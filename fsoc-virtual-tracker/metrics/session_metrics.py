"""Extended per-run metrics required by SIH performance reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionMetrics:
    """Accumulates SIH-oriented performance statistics for one simulation run."""

    processing_times_ms: list[float] = field(default_factory=list)
    pixel_errors: list[float] = field(default_factory=list)
    acquisition_durations_s: list[float] = field(default_factory=list)

    locked_seconds: float = 0.0
    coasting_seconds: float = 0.0
    lost_seconds: float = 0.0
    runtime_seconds: float = 0.0

    _lost_since: float | None = None

    def record_frame(
        self,
        dt: float,
        tracking_state: str,
        pixel_error: float,
        processing_time_ms: float,
        elapsed_s: float,
    ) -> None:
        self.runtime_seconds += dt
        self.pixel_errors.append(pixel_error)
        self.processing_times_ms.append(processing_time_ms)

        if tracking_state == "LOCKED":
            self.locked_seconds += dt
            if self._lost_since is not None:
                self.acquisition_durations_s.append(elapsed_s - self._lost_since)
                self._lost_since = None
        elif tracking_state == "LOST":
            self.lost_seconds += dt
            if self._lost_since is None:
                self._lost_since = elapsed_s
        else:
            self.coasting_seconds += dt

    @property
    def avg_pixel_error(self) -> float:
        if not self.pixel_errors:
            return 0.0
        return sum(self.pixel_errors) / len(self.pixel_errors)

    @property
    def max_pixel_error(self) -> float:
        return max(self.pixel_errors) if self.pixel_errors else 0.0

    @property
    def lock_retention_pct(self) -> float:
        if self.runtime_seconds <= 0.0:
            return 0.0
        return 100.0 * self.locked_seconds / self.runtime_seconds

    @property
    def avg_processing_time_ms(self) -> float:
        if not self.processing_times_ms:
            return 0.0
        return sum(self.processing_times_ms) / len(self.processing_times_ms)

    @property
    def max_processing_time_ms(self) -> float:
        return max(self.processing_times_ms) if self.processing_times_ms else 0.0

    @property
    def avg_acquisition_time_s(self) -> float:
        if not self.acquisition_durations_s:
            return 0.0
        return sum(self.acquisition_durations_s) / len(self.acquisition_durations_s)

    def to_summary_dict(
        self, *, fps_avg: float, active_detector: str, reacquisition_count: int
    ) -> dict:
        runtime = max(self.runtime_seconds, 1e-6)
        return {
            "simulation_duration_s": round(self.runtime_seconds, 2),
            "avg_fps": round(fps_avg, 2),
            "avg_pixel_error_px": round(self.avg_pixel_error, 4),
            "max_pixel_error_px": round(self.max_pixel_error, 4),
            "lock_retention_pct": round(self.lock_retention_pct, 2),
            "avg_acquisition_time_s": round(self.avg_acquisition_time_s, 3),
            "acquisition_event_count": len(self.acquisition_durations_s),
            "avg_processing_time_ms": round(self.avg_processing_time_ms, 3),
            "max_processing_time_ms": round(self.max_processing_time_ms, 3),
            "pct_locked": round(100.0 * self.locked_seconds / runtime, 2),
            "pct_coasting": round(100.0 * self.coasting_seconds / runtime, 2),
            "pct_lost": round(100.0 * self.lost_seconds / runtime, 2),
            "reacquisition_count": reacquisition_count,
            "active_detector": active_detector,
        }

    def write_summary(self, path: Path, **kwargs) -> None:
        path.write_text(json.dumps(self.to_summary_dict(**kwargs), indent=2), encoding="utf-8")
