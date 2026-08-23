"""Link readiness scoring for coarse-to-fine FSOC handoff decision support.

This module estimates whether the current coarse-tracking performance, together
with the active disturbance severity, would likely be good enough to hand off
to a fine-pointing stage in a real free-space optical communication (FSOC) system.

The score is a decision-support heuristic, not a certified link-budget, BER, or
outage calculation. It combines normalized tracking error, turbulence, vibration,
and lock-state inputs into a single 0-1 readiness value for live demos and
reports.
"""

from __future__ import annotations

from dataclasses import dataclass

from disturbance.disturbance import TurbulenceModel, VibrationModel
from tracker.kalman_tracker import (
    TRACKING_COASTING,
    TRACKING_LOCKED,
    TRACKING_LOST,
)

# v1 weighted heuristic. This is NOT a physical BER/outage model.
WEIGHT_PIXEL_ERROR = 0.40
WEIGHT_TURBULENCE = 0.20
WEIGHT_VIBRATION = 0.20
WEIGHT_TRACKING_STATE = 0.20

COASTING_STATE_FACTOR = 0.35


@dataclass(frozen=True)
class LinkReadinessResult:
    score: float
    pixel_error_subscore: float
    turbulence_subscore: float
    vibration_subscore: float
    tracking_state_subscore: float


class LinkReadinessScore:
    """Compute a 0-1 coarse-tracking handoff readiness score each frame."""

    def __init__(
        self,
        fov_width: float,
        fov_height: float,
        error_reference: float | None = None,
    ) -> None:
        self.fov_width = fov_width
        self.fov_height = fov_height
        self.error_reference = error_reference or min(fov_width, fov_height)

    def compute(
        self,
        pixel_error: float,
        turbulence_strength: float,
        vibration_amplitude: float,
        tracking_state: str,
    ) -> LinkReadinessResult:
        pixel_error_subscore = self._normalize_pixel_error(pixel_error)
        turbulence_subscore = self._normalize_inverse(
            turbulence_strength,
            TurbulenceModel.MAX_STRENGTH,
        )
        vibration_subscore = self._normalize_inverse(
            vibration_amplitude,
            VibrationModel.MAX_AMPLITUDE,
        )
        tracking_state_subscore = self._tracking_state_subscore(tracking_state)

        if tracking_state == TRACKING_LOST:
            score = 0.0
        else:
            # Weighted v1 formula: better sub-scores and LOCKED state raise readiness.
            score = (
                WEIGHT_PIXEL_ERROR * pixel_error_subscore
                + WEIGHT_TURBULENCE * turbulence_subscore
                + WEIGHT_VIBRATION * vibration_subscore
                + WEIGHT_TRACKING_STATE * tracking_state_subscore
            )
            score = self._clamp(score)

        return LinkReadinessResult(
            score=score,
            pixel_error_subscore=pixel_error_subscore,
            turbulence_subscore=turbulence_subscore,
            vibration_subscore=vibration_subscore,
            tracking_state_subscore=tracking_state_subscore,
        )

    def _normalize_pixel_error(self, pixel_error: float) -> float:
        normalized_error = self._clamp(pixel_error / max(self.error_reference, 1.0))
        return 1.0 - normalized_error

    @staticmethod
    def _normalize_inverse(value: float, maximum: float) -> float:
        if maximum <= 0.0:
            return 1.0
        return 1.0 - LinkReadinessScore._clamp(value / maximum)

    @staticmethod
    def _tracking_state_subscore(tracking_state: str) -> float:
        if tracking_state == TRACKING_LOCKED:
            return 1.0
        if tracking_state == TRACKING_COASTING:
            return COASTING_STATE_FACTOR
        return 0.0

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
