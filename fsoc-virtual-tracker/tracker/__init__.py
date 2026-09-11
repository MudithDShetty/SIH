"""Tracker package: constant-velocity Kalman filter and LOCKED/COASTING/LOST states."""

from tracker.kalman_tracker import (
    LOST_FRAME_THRESHOLD,
    TRACKING_COASTING,
    TRACKING_LOCKED,
    TRACKING_LOST,
    BeaconTracker,
)

__all__ = [
    "LOST_FRAME_THRESHOLD",
    "TRACKING_COASTING",
    "TRACKING_LOCKED",
    "TRACKING_LOST",
    "BeaconTracker",
]
