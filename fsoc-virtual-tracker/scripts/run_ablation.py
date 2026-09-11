#!/usr/bin/env python3
"""Ablation: classical vs AI on matched-seed short runs.

Metrics emphasize PAT-relevant KPIs: lock retention, re-acquisitions,
mean/RMS angular error (µrad) — not mean pixel error alone.
"""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Classical vs AI ablation table")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--turbulence", type=float, default=4.0)
    parser.add_argument("--vibration", type=float, default=8.0)
    parser.add_argument("--sensor-noise", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Only summarize existing classical_*.csv / ai_*.csv",
    )
    args = parser.parse_args()

    if not args.skip_run:
        print(
            "Running matched classical vs AI via scripts/run_comparison.py "
            f"({args.duration}s, turb={args.turbulence}, vib={args.vibration})..."
        )
        sys.argv = [
            "run_comparison.py",
            "--duration",
            str(args.duration),
            "--turbulence",
            str(args.turbulence),
            "--vibration",
            str(args.vibration),
            "--sensor-noise",
            str(args.sensor_noise),
            "--seed",
            str(args.seed),
        ]
        try:
            runpy.run_path(str(ROOT / "scripts" / "run_comparison.py"), run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise

    logs = ROOT / "logs"
    classical = sorted(logs.glob("classical_*.csv"))
    ai = sorted(logs.glob("ai_*.csv"))
    if not classical or not ai:
        print("No comparison CSVs found; ablation summary skipped.")
        return

    from report import load_run_csv, summarize_run

    c_path, a_path = classical[-1], ai[-1]
    c_sum = summarize_run(load_run_csv(c_path), c_path.name)
    a_sum = summarize_run(load_run_csv(a_path), a_path.name)

    table = {
        "settings": {
            "duration_s": args.duration,
            "turbulence": args.turbulence,
            "vibration": args.vibration,
            "sensor_noise": args.sensor_noise,
            "seed": args.seed,
        },
        "classical": {
            "file": c_path.name,
            "avg_pixel_error_px": round(c_sum.avg_pixel_error, 3),
            "avg_angular_error_urad": round(c_sum.avg_angular_error_urad, 1),
            "lock_pct": round(c_sum.pct_locked, 2),
            "reacquisitions": c_sum.total_reacquisitions,
            "handoffs": c_sum.handoff_count,
            "avg_readiness": round(c_sum.avg_link_readiness, 3),
        },
        "ai": {
            "file": a_path.name,
            "avg_pixel_error_px": round(a_sum.avg_pixel_error, 3),
            "avg_angular_error_urad": round(a_sum.avg_angular_error_urad, 1),
            "lock_pct": round(a_sum.pct_locked, 2),
            "reacquisitions": a_sum.total_reacquisitions,
            "handoffs": a_sum.handoff_count,
            "avg_readiness": round(a_sum.avg_link_readiness, 3),
        },
        "narrative": (
            "Report AI wins on lock retention / re-acq count when present; "
            "report classical wins on mean error honestly when present."
        ),
    }
    out = logs / "ablation_summary.json"
    out.write_text(json.dumps(table, indent=2), encoding="utf-8")
    print(json.dumps(table, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
