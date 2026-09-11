#!/usr/bin/env python3
"""Synthesize a Benchmark-2 style MP4 + GT CSV for local smoke tests.

Full-frame moving beacon with selectable noise (no virtual PTZ).
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "logs" / "benchmark2" / "ps_sample.mp4")
    parser.add_argument("--gt", type=Path, default=ROOT / "logs" / "benchmark2" / "ps_sample_gt.csv")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--noise", choices=("gaussian", "salt_pepper", "poisson", "none"), default="gaussian")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    frames = int(args.seconds * args.fps)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(args.out), fourcc, float(args.fps), (args.width, args.height))
    if not writer.isOpened():
        print("Failed to open VideoWriter")
        return 1

    gt_rows = []
    cx0, cy0 = args.width * 0.3, args.height * 0.5
    for i in range(frames):
        t = i / args.fps
        # Figure-8-ish path across the full frame.
        x = cx0 + 0.35 * args.width * math.sin(0.7 * t)
        y = cy0 + 0.25 * args.height * math.sin(1.4 * t)
        img = np.zeros((args.height, args.width, 3), dtype=np.uint8)
        img[:] = (12, 10, 8)
        # Soft beacon blob ~10 px class
        cv2.circle(img, (int(x), int(y)), 6, (240, 240, 255), -1)
        cv2.circle(img, (int(x), int(y)), 3, (255, 255, 255), -1)

        if args.noise == "gaussian":
            noise = np.random.normal(0, 12, img.shape).astype(np.float32)
            img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        elif args.noise == "salt_pepper":
            mask = np.random.rand(args.height, args.width) < 0.04
            img[mask] = 255
            mask2 = np.random.rand(args.height, args.width) < 0.04
            img[mask2] = 0
        elif args.noise == "poisson":
            # Approximate Poisson via scaled Gaussian on intensities.
            vals = np.random.poisson(img.astype(np.float32) * 0.35) / 0.35
            img = np.clip(vals, 0, 255).astype(np.uint8)

        writer.write(img)
        gt_rows.append({"frame": i, "x": round(x, 3), "y": round(y, 3)})

    writer.release()
    with args.gt.open("w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=["frame", "x", "y"])
        w.writeheader()
        w.writerows(gt_rows)

    print(f"Wrote {args.out}")
    print(f"Wrote {args.gt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
