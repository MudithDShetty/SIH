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
    angular_errors_urad: list[float] = field(default_factory=list)
    acquisition_durations_s: list[float] = field(default_factory=list)

    locked_seconds: float = 0.0
    coasting_seconds: float = 0.0
    lost_seconds: float = 0.0
    fine_seconds: float = 0.0
    runtime_seconds: float = 0.0
    handoff_count: int = 0

    _lost_since: float | None = None

    def record_frame(
        self,
        dt: float,
        tracking_state: str,
        pixel_error: float,
        processing_time_ms: float,
        elapsed_s: float,
        *,
        angular_error_urad: float = 0.0,
        pat_stage: str = "COARSE",
        handoff_count: int = 0,
    ) -> None:
        self.runtime_seconds += dt
        self.pixel_errors.append(pixel_error)
        self.angular_errors_urad.append(angular_error_urad)
        self.processing_times_ms.append(processing_time_ms)
        self.handoff_count = handoff_count
        if pat_stage == "FINE":
            self.fine_seconds += dt

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
    def avg_angular_error_urad(self) -> float:
        if not self.angular_errors_urad:
            return 0.0
        return sum(self.angular_errors_urad) / len(self.angular_errors_urad)

    @property
    def rms_angular_error_urad(self) -> float:
        if not self.angular_errors_urad:
            return 0.0
        return (
            sum(e * e for e in self.angular_errors_urad) / len(self.angular_errors_urad)
        ) ** 0.5

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
    def p50_processing_time_ms(self) -> float:
        return self._percentile(self.processing_times_ms, 50)

    @property
    def p95_processing_time_ms(self) -> float:
        return self._percentile(self.processing_times_ms, 95)

    @property
    def avg_acquisition_time_s(self) -> float:
        if not self.acquisition_durations_s:
            return 0.0
        return sum(self.acquisition_durations_s) / len(self.acquisition_durations_s)

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
        return ordered[index]

    def to_summary_dict(
        self,
        *,
        fps_avg: float,
        active_detector: str,
        reacquisition_count: int,
        profile: str = "physics",
        log_csv: str | None = None,
    ) -> dict:
        """Build SIH-complete summary JSON (duration, FPS, errors, lock, Tacq, latency)."""
        runtime = max(self.runtime_seconds, 1e-6)
        sih_required = {
            "simulation_duration_s": round(self.runtime_seconds, 2),
            "fps": round(fps_avg, 2),
            "tracking_error_px_avg": round(self.avg_pixel_error, 4),
            "tracking_error_px_max": round(self.max_pixel_error, 4),
            "tracking_error_urad_avg": round(self.avg_angular_error_urad, 2),
            "tracking_error_urad_rms": round(self.rms_angular_error_urad, 2),
            "lock_retention_pct": round(self.lock_retention_pct, 2),
            "acquisition_time_s_avg": round(self.avg_acquisition_time_s, 3),
            "acquisition_event_count": len(self.acquisition_durations_s),
            "processing_time_ms_avg": round(self.avg_processing_time_ms, 3),
            "processing_time_ms_max": round(self.max_processing_time_ms, 3),
            "processing_time_ms_p95": round(self.p95_processing_time_ms, 3),
            "reacquisition_count": reacquisition_count,
            "active_detector": active_detector,
        }
        return {
            "schema_version": "sih26169-1.1",
            "profile": profile,
            "log_csv": log_csv,
            "sih_required": sih_required,
            # Flat aliases (backward compatible with existing report tooling)
            "simulation_duration_s": sih_required["simulation_duration_s"],
            "avg_fps": sih_required["fps"],
            "avg_pixel_error_px": sih_required["tracking_error_px_avg"],
            "max_pixel_error_px": sih_required["tracking_error_px_max"],
            "avg_angular_error_urad": sih_required["tracking_error_urad_avg"],
            "rms_angular_error_urad": sih_required["tracking_error_urad_rms"],
            "lock_retention_pct": sih_required["lock_retention_pct"],
            "avg_acquisition_time_s": sih_required["acquisition_time_s_avg"],
            "acquisition_event_count": sih_required["acquisition_event_count"],
            "avg_processing_time_ms": sih_required["processing_time_ms_avg"],
            "max_processing_time_ms": sih_required["processing_time_ms_max"],
            "p50_processing_time_ms": round(self.p50_processing_time_ms, 3),
            "p95_processing_time_ms": sih_required["processing_time_ms_p95"],
            "pct_locked": round(100.0 * self.locked_seconds / runtime, 2),
            "pct_coasting": round(100.0 * self.coasting_seconds / runtime, 2),
            "pct_lost": round(100.0 * self.lost_seconds / runtime, 2),
            "pct_fine": round(100.0 * self.fine_seconds / runtime, 2),
            "handoff_count": self.handoff_count,
            "reacquisition_count": reacquisition_count,
            "active_detector": active_detector,
        }

    def write_summary(self, path: Path, **kwargs) -> None:
        path.write_text(json.dumps(self.to_summary_dict(**kwargs), indent=2), encoding="utf-8")
