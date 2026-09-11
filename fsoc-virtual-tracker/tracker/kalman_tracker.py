import math

import numpy as np
from filterpy.kalman import KalmanFilter

LOST_FRAME_THRESHOLD = 15

TRACKING_LOCKED = "LOCKED"
TRACKING_COASTING = "COASTING"
TRACKING_LOST = "LOST"


class BeaconTracker:
    """Constant-velocity Kalman tracker for beacon position in scene coordinates."""

    def __init__(
        self,
        initial_x: float = 0.0,
        initial_y: float = 0.0,
        process_noise: float = 25.0,
        measurement_noise: float = 4.0,
    ) -> None:
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.frames_since_measurement = LOST_FRAME_THRESHOLD + 1
        self.has_measurement = False

        self.kf = KalmanFilter(dim_x=4, dim_z=2)
        self.kf.x = np.array([initial_x, initial_y, 0.0, 0.0], dtype=float)
        self.kf.F = np.eye(4)
        self.kf.H = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
            ]
        )
        self.kf.P *= 500.0
        self.kf.R = np.eye(2) * measurement_noise
        self.kf.Q = np.eye(4) * process_noise

    def predict(self, dt: float) -> None:
        dt = max(dt, 1e-6)
        self.kf.F = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        q = self.process_noise
        self.kf.Q = np.array(
            [
                [dt**4 / 4 * q, 0.0, dt**3 / 2 * q, 0.0],
                [0.0, dt**4 / 4 * q, 0.0, dt**3 / 2 * q],
                [dt**3 / 2 * q, 0.0, dt**2 * q, 0.0],
                [0.0, dt**3 / 2 * q, 0.0, dt**2 * q],
            ]
        )
        self.kf.predict()

    def update(self, measured_x: float, measured_y: float) -> None:
        self.kf.update(np.array([measured_x, measured_y], dtype=float))
        self.frames_since_measurement = 0
        self.has_measurement = True

    def mark_missed_measurement(self) -> None:
        self.frames_since_measurement += 1

    def force_lost(self) -> None:
        """Force LOST state (e.g. detector switch with no valid re-lock)."""
        self.frames_since_measurement = LOST_FRAME_THRESHOLD + 1

    def reset(self, x: float, y: float) -> None:
        self.kf.x = np.array([x, y, 0.0, 0.0], dtype=float)
        self.kf.P = np.eye(4) * 500.0
        self.frames_since_measurement = 0
        self.has_measurement = True

    def get_velocity(self) -> tuple[float, float]:
        return float(self.kf.x[2]), float(self.kf.x[3])

    def get_estimate(self) -> tuple[float, float, float]:
        position_covariance_trace = float(self.kf.P[0, 0] + self.kf.P[1, 1])
        confidence = 1.0 / (1.0 + position_covariance_trace)
        return float(self.kf.x[0]), float(self.kf.x[1]), confidence

    def position_sigma_px(self) -> float:
        """1-sigma position uncertainty radius from covariance diagonal (px)."""
        return float(math.sqrt(max(self.kf.P[0, 0] + self.kf.P[1, 1], 0.0)))

    def get_tracking_state(self) -> str:
        if not self.has_measurement:
            return TRACKING_LOST
        if self.frames_since_measurement == 0:
            return TRACKING_LOCKED
        if self.frames_since_measurement <= LOST_FRAME_THRESHOLD:
            return TRACKING_COASTING
        return TRACKING_LOST

    def should_drive_camera(self) -> bool:
        return self.get_tracking_state() != TRACKING_LOST
