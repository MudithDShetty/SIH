#!/usr/bin/env python3
"""SIH26169 Benchmark Performance-2: external MP4 coarse pointing (PTZ bypass).

Judges supply full-screen noisy beacon videos @ ~30 fps. This tool:
  - reads the video frames (no virtual pan-tilt / scene camera)
  - runs Classical or AI+fusion detection on each full frame
  - optional Kalman coast/lost logic in image coordinates
  - writes SIH performance CSV + JSON summary

Usage:
  python scripts/benchmark_video.py --video path.mp4
  python scripts/benchmark_video.py --video path.mp4 --detector ai
  python scripts/benchmark_video.py --video path.mp4 --gt path_gt.csv

GT CSV columns (optional): frame,x,y
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from detector.classical_detector import ClassicalDetector
from tracker.kalman_tracker import (
    TRACKING_COASTING,
    TRACKING_LOCKED,
    TRACKING_LOST,
    BeaconTracker,
)


def load_gt(path: Path | None) -> dict[int, tuple[float, float]]:
    if path is None or not path.is_file():
        return {}
    gt: dict[int, tuple[float, float]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            frame = int(float(row["frame"]))
            gt[frame] = (float(row["x"]), float(row["y"]))
    return gt


def build_detector(name: str):
    classical = ClassicalDetector()
    if name == "classical":
        return classical, "classical"
    try:
        from detector.ai_detector import AIDetector
        from detector.hybrid_detector import HybridDetector

        return HybridDetector(AIDetector(), classical), "ai+fusion"
    except Exception as exc:  # noqa: BLE001
        print(f"AI unavailable ({exc}); using classical.")
        return classical, "classical"


def main() -> int:
    parser = argparse.ArgumentParser(description="SIH Benchmark-2 video coarse pointing")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--detector", choices=("classical", "ai"), default="classical")
    parser.add_argument("--gt", type=Path, default=None, help="Optional GT CSV frame,x,y")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "logs" / "benchmark2",
    )
    parser.add_argument("--max-frames", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    if not args.video.is_file():
        print(f"Missing video: {args.video}")
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.video.stem
    csv_path = args.out_dir / f"{stem}_{args.detector}_centroid.csv"
    json_path = args.out_dir / f"{stem}_{args.detector}_summary.json"

    detector, detector_name = build_detector(args.detector)
    gt = load_gt(args.gt)
    tracker = BeaconTracker(0.0, 0.0)

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        print(f"Could not open video: {args.video}")
        return 1

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    dt = 1.0 / max(fps, 1e-6)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    rows: list[dict] = []
    errors: list[float] = []
    proc_ms: list[float] = []
    locked = coasting = lost = 0
    acq_times: list[float] = []
    reacq_times: list[float] = []
    first_lock_s: float | None = None
    lost_since: float | None = None
    reacq_count = 0
    prev_state = TRACKING_LOST
    frame_idx = 0
    t0 = time.perf_counter()

    use_ai = detector_name.startswith("ai")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if args.max_frames and frame_idx >= args.max_frames:
            break

        t_frame = time.perf_counter()
        tracker.predict(dt)
        was_lost = tracker.get_tracking_state() == TRACKING_LOST

        if use_ai:
            det = detector.detect(frame, noise_level=0.2, reacquiring=was_lost)
        else:
            det = detector.detect(frame, adaptive=True)

        if det is not None:
            if was_lost:
                tracker.reset(det[0], det[1])
                if lost_since is not None:
                    reacq_times.append(frame_idx * dt - lost_since)
                    reacq_count += 1
                    lost_since = None
            else:
                tracker.update(det[0], det[1])
        else:
            tracker.mark_missed_measurement()

        est_x, est_y, _ = tracker.get_estimate()
        state = tracker.get_tracking_state()
        elapsed = frame_idx * dt

        if state == TRACKING_LOCKED:
            locked += 1
            if first_lock_s is None:
                first_lock_s = elapsed
                acq_times.append(elapsed)
        elif state == TRACKING_COASTING:
            coasting += 1
        else:
            lost += 1
            if prev_state != TRACKING_LOST:
                lost_since = elapsed

        prev_state = state
        proc = (time.perf_counter() - t_frame) * 1000.0
        proc_ms.append(proc)

        err = float("nan")
        if frame_idx in gt and det is not None:
            gx, gy = gt[frame_idx]
            err = math.hypot(det[0] - gx, det[1] - gy)
            errors.append(err)

        rows.append(
            {
                "frame": frame_idx,
                "time_s": round(elapsed, 4),
                "det_x": "" if det is None else round(det[0], 3),
                "det_y": "" if det is None else round(det[1], 3),
                "est_x": round(est_x, 3),
                "est_y": round(est_y, 3),
                "tracking_state": state,
                "centroid_error_px": "" if math.isnan(err) else round(err, 4),
                "processing_ms": round(proc, 3),
            }
        )
        frame_idx += 1

    cap.release()
    wall_s = time.perf_counter() - t0
    n = max(frame_idx, 1)
    lock_pct = 100.0 * locked / n
    avg_fps = n / max(wall_s, 1e-6)

    def _avg(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    summary = {
        "benchmark": "SIH26169-Benchmark-2",
        "video": str(args.video),
        "detector": detector_name,
        "frame_count": frame_idx,
        "resolution": [width, height],
        "video_fps": fps,
        "simulation_duration_s": round(frame_idx * dt, 3),
        "wall_clock_s": round(wall_s, 3),
        "avg_fps": round(avg_fps, 2),
        "acquisition_time_s": (
            round(first_lock_s, 4) if first_lock_s is not None else -1.0
        ),
        "avg_reacquisition_time_s": round(_avg(reacq_times), 4),
        "reacquisition_count": reacq_count,
        "lock_retention_pct": round(lock_pct, 2),
        "target_loss_pct": round(100.0 - lock_pct, 2),
        "avg_centroid_error_px": round(_avg(errors), 4) if errors else None,
        "max_centroid_error_px": round(max(errors), 4) if errors else None,
        "rmse_centroid_error_px": (
            round(math.sqrt(sum(e * e for e in errors) / len(errors)), 4) if errors else None
        ),
        "avg_processing_time_ms": round(_avg(proc_ms), 3),
        "max_processing_time_ms": round(max(proc_ms) if proc_ms else 0.0, 3),
        "pct_locked": round(100.0 * locked / n, 2),
        "pct_coasting": round(100.0 * coasting / n, 2),
        "pct_lost": round(100.0 * lost / n, 2),
        "gt_frames": len(errors),
        "ptz_bypassed": True,
    }

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["frame"])
        writer.writeheader()
        writer.writerows(rows)

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {csv_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
