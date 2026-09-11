"""Link readiness scoring for coarse-to-fine FSOC handoff decision support.

v2 prefers a physics-informed SNR / fade-margin score from ``OpticalLink`` when
available, and falls back to the original weighted heuristic otherwise.

Still a decision-support signal — not a certified BER or outage calculation.
"""

from __future__ import annotations

from dataclasses import dataclass

from disturbance.disturbance import TurbulenceModel, VibrationModel
from tracker.kalman_tracker import (
    TRACKING_COASTING,
    TRACKING_LOCKED,
    TRACKING_LOST,
)

# Legacy heuristic weights (fallback when SNR is not supplied).
WEIGHT_PIXEL_ERROR = 0.40
WEIGHT_TURBULENCE = 0.20
WEIGHT_VIBRATION = 0.20
WEIGHT_TRACKING_STATE = 0.20

# Physics-informed blend when SNR is available.
WEIGHT_SNR = 0.45
WEIGHT_POINTING = 0.25
WEIGHT_CHANNEL = 0.15
WEIGHT_LOCK = 0.15

COASTING_STATE_FACTOR = 0.35
SNR_HANDOFF_DB = 10.0
SNR_EXCELLENT_DB = 25.0


@dataclass(frozen=True)
class LinkReadinessResult:
    score: float
    pixel_error_subscore: float
    turbulence_subscore: float
    vibration_subscore: float
    tracking_state_subscore: float
    snr_db: float | None = None
    fade_margin_db: float | None = None
    mode: str = "heuristic"


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
        *,
        snr_db: float | None = None,
        fade_margin_db: float | None = None,
        pointing_loss: float | None = None,
        scintillation: float | None = None,
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
            return LinkReadinessResult(
                score=0.0,
                pixel_error_subscore=pixel_error_subscore,
                turbulence_subscore=turbulence_subscore,
                vibration_subscore=vibration_subscore,
                tracking_state_subscore=tracking_state_subscore,
                snr_db=snr_db,
                fade_margin_db=fade_margin_db,
                mode="lost",
            )

        if snr_db is not None:
            snr_sub = self._clamp(
                (snr_db - SNR_HANDOFF_DB) / (SNR_EXCELLENT_DB - SNR_HANDOFF_DB)
            )
            pointing_sub = (
                self._clamp(pointing_loss)
                if pointing_loss is not None
                else pixel_error_subscore
            )
            if scintillation is not None:
                # Penalize deep fades (I << 1) more than bright spikes.
                channel_sub = self._clamp(min(1.0, scintillation))
            else:
                channel_sub = 0.5 * (turbulence_subscore + vibration_subscore)

            score = (
                WEIGHT_SNR * snr_sub
                + WEIGHT_POINTING * pointing_sub
                + WEIGHT_CHANNEL * channel_sub
                + WEIGHT_LOCK * tracking_state_subscore
            )
            return LinkReadinessResult(
                score=self._clamp(score),
                pixel_error_subscore=pixel_error_subscore,
                turbulence_subscore=turbulence_subscore,
                vibration_subscore=vibration_subscore,
                tracking_state_subscore=tracking_state_subscore,
                snr_db=snr_db,
                fade_margin_db=fade_margin_db,
                mode="snr",
            )

        score = (
            WEIGHT_PIXEL_ERROR * pixel_error_subscore
            + WEIGHT_TURBULENCE * turbulence_subscore
            + WEIGHT_VIBRATION * vibration_subscore
            + WEIGHT_TRACKING_STATE * tracking_state_subscore
        )
        return LinkReadinessResult(
            score=self._clamp(score),
            pixel_error_subscore=pixel_error_subscore,
            turbulence_subscore=turbulence_subscore,
            vibration_subscore=vibration_subscore,
            tracking_state_subscore=tracking_state_subscore,
            snr_db=snr_db,
            fade_margin_db=fade_margin_db,
            mode="heuristic",
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
