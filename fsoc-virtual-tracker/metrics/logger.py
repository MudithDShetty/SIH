"""Performance CSV / run-sheet logger for BeamLock live sessions.

Writes once-per-second rows (see ``metrics.csv_schema.CSV_COLUMNS``) and a
``.runsheet.json`` next to the CSV. Session aggregates (SIH-required duration,
FPS, tracking error, lock retention, acquisition time, processing latency) are
produced by ``SessionMetrics`` as ``*.summary.json``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tracker.kalman_tracker import TRACKING_COASTING, TRACKING_LOCKED, TRACKING_LOST

from metrics.csv_schema import CSV_COLUMNS


@dataclass(frozen=True)
class LogSnapshot:
    fps: float
    tracking_state: str
    pixel_error: float
    turbulence_strength: float
    vibration_amplitude: float
    sensor_noise_level: float
    link_readiness_score: float
    cumulative_lost_seconds: float
    reacquisition_count: int
    active_detector: str
    angular_error_urad: float = 0.0
    boresight_urad: float = 0.0
    az_urad: float = 0.0
    el_urad: float = 0.0
    pat_stage: str = "COARSE"
    handoff_count: int = 0


class RunLogger:
    """Append once-per-second performance rows to a CSV performance log."""

    def __init__(self, log_path: Path, run_config: dict[str, Any] | None = None) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_config = run_config or {}

        self._file = self.log_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=CSV_COLUMNS)
        self._writer.writeheader()
        self._file.flush()

        self._start_monotonic: float | None = None
        self._last_log_elapsed = 0.0
        self._row_count = 0

        self._runtime_seconds = 0.0
        self._pixel_error_sum = 0.0
        self._angular_error_sum = 0.0
        self._fps_sum = 0.0
        self._readiness_sum = 0.0
        self._frame_count = 0
        self._state_seconds = {
            TRACKING_LOCKED: 0.0,
            TRACKING_COASTING: 0.0,
            TRACKING_LOST: 0.0,
        }
        self._last_reacquisition_count = 0
        self._last_handoff_count = 0
        self._angular_errors: list[float] = []

        if self.run_config:
            self.write_run_sheet(self.run_config)

    @classmethod
    def create_default(
        cls,
        logs_dir: Path | None = None,
        run_config: dict[str, Any] | None = None,
    ) -> RunLogger:
        root = Path(__file__).resolve().parents[1]
        directory = logs_dir or (root / "logs")
        filename = f"run_{datetime.now():%Y-%m-%d_%H%M}.csv"
        return cls(directory / filename, run_config=run_config)

    def write_run_sheet(self, config: dict[str, Any]) -> Path:
        """Write PAT run sheet JSON next to the CSV (seed, config, git-ish metadata)."""
        sheet = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "log_csv": self.log_path.name,
            **config,
        }
        path = self.log_path.with_suffix(".runsheet.json")
        path.write_text(json.dumps(sheet, indent=2), encoding="utf-8")
        return path

    def record_frame(
        self,
        tracking_state: str,
        dt: float,
        fps: float,
        pixel_error: float,
        link_readiness_score: float,
        angular_error_urad: float = 0.0,
    ) -> None:
        if self._start_monotonic is None:
            self._start_monotonic = 0.0

        self._runtime_seconds += dt
        self._frame_count += 1
        self._pixel_error_sum += pixel_error
        self._angular_error_sum += angular_error_urad
        self._angular_errors.append(angular_error_urad)
        self._fps_sum += fps
        self._readiness_sum += link_readiness_score
        if tracking_state in self._state_seconds:
            self._state_seconds[tracking_state] += dt

    def maybe_log_second(self, snapshot: LogSnapshot) -> None:
        elapsed = self._runtime_seconds
        if elapsed - self._last_log_elapsed < 1.0:
            return

        self._writer.writerow(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "fps": f"{snapshot.fps:.2f}",
                "tracking_state": snapshot.tracking_state,
                "pixel_error": f"{snapshot.pixel_error:.4f}",
                "angular_error_urad": f"{snapshot.angular_error_urad:.4f}",
                "boresight_urad": f"{snapshot.boresight_urad:.4f}",
                "az_urad": f"{snapshot.az_urad:.4f}",
                "el_urad": f"{snapshot.el_urad:.4f}",
                "pat_stage": snapshot.pat_stage,
                "handoff_count": snapshot.handoff_count,
                "turbulence_strength": f"{snapshot.turbulence_strength:.4f}",
                "vibration_amplitude": f"{snapshot.vibration_amplitude:.4f}",
                "sensor_noise_level": f"{snapshot.sensor_noise_level:.4f}",
                "link_readiness_score": f"{snapshot.link_readiness_score:.4f}",
                "cumulative_lost_seconds": f"{snapshot.cumulative_lost_seconds:.2f}",
                "reacquisition_count": snapshot.reacquisition_count,
                "active_detector": snapshot.active_detector,
            }
        )
        self._file.flush()
        self._row_count += 1
        self._last_log_elapsed = elapsed
        self._last_reacquisition_count = snapshot.reacquisition_count
        self._last_handoff_count = snapshot.handoff_count

    def close(self) -> None:
        if self._file.closed:
            return

        self._file.flush()
        self._file.close()
        self._print_summary()

    def _print_summary(self) -> None:
        runtime = self._runtime_seconds
        frames = max(self._frame_count, 1)
        avg_pixel_error = self._pixel_error_sum / frames
        avg_angular = self._angular_error_sum / frames
        avg_fps = self._fps_sum / frames
        avg_readiness = self._readiness_sum / frames
        rms_urad = 0.0
        if self._angular_errors:
            rms_urad = (
                sum(e * e for e in self._angular_errors) / len(self._angular_errors)
            ) ** 0.5

        locked_pct = 100.0 * self._state_seconds[TRACKING_LOCKED] / max(runtime, 1e-6)
        coasting_pct = 100.0 * self._state_seconds[TRACKING_COASTING] / max(runtime, 1e-6)
        lost_pct = 100.0 * self._state_seconds[TRACKING_LOST] / max(runtime, 1e-6)

        print("\n=== FSOC Virtual Tracker Performance Log ===")
        print(f"CSV file: {self.log_path}")
        print(f"Logged rows: {self._row_count}")
        print(f"Total runtime: {runtime:.1f}s")
        print(f"Average pixel error: {avg_pixel_error:.2f} px")
        print(f"Average / RMS angular error: {avg_angular:.1f} / {rms_urad:.1f} urad")
        print(f"Average FPS: {avg_fps:.1f}")
        print(f"Average link readiness: {avg_readiness:.3f}")
        print(f"Total re-acquisitions: {self._last_reacquisition_count}")
        print(f"Fine handoffs: {self._last_handoff_count}")
        print(
            "Tracking time: "
            f"LOCKED {locked_pct:.1f}% | "
            f"COASTING {coasting_pct:.1f}% | "
            f"LOST {lost_pct:.1f}%"
        )
        print("============================================\n")
