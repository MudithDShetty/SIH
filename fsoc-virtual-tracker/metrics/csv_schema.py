"""CSV column names for BeamLock / SIH26169 performance logs.

SIH-oriented fields (also aggregated into ``*.summary.json``):
  - simulation duration / FPS
  - tracking error (pixel + µrad)
  - lock retention (via tracking_state time fractions)
  - re-acquisition count
  - processing latency (session summary)
  - acquisition time (session summary)
"""

# Always written by current RunLogger (one row per second).
CSV_COLUMNS = [
    "timestamp",
    "fps",
    "tracking_state",
    "pixel_error",
    "angular_error_urad",
    "boresight_urad",
    "az_urad",
    "el_urad",
    "pat_stage",
    "handoff_count",
    "turbulence_strength",
    "vibration_amplitude",
    "sensor_noise_level",
    "link_readiness_score",
    "cumulative_lost_seconds",
    "reacquisition_count",
    "active_detector",
]

# Required for old logs to still load in report.py.
LEGACY_REQUIRED_COLUMNS = [
    "timestamp",
    "fps",
    "tracking_state",
    "pixel_error",
    "turbulence_strength",
    "vibration_amplitude",
    "sensor_noise_level",
    "link_readiness_score",
    "cumulative_lost_seconds",
    "reacquisition_count",
    "active_detector",
]

OPTIONAL_COLUMNS = [
    "angular_error_urad",
    "boresight_urad",
    "az_urad",
    "el_urad",
    "pat_stage",
    "handoff_count",
]

# Human-readable SIH mapping for documentation / report.py.
SIH_METRIC_MAP = {
    "simulation_duration_s": "Total simulation / demo duration (seconds)",
    "avg_fps": "Average frames per second",
    "avg_pixel_error_px": "Average tracking error (pixels)",
    "max_pixel_error_px": "Maximum tracking error (pixels)",
    "avg_angular_error_urad": "Average pointing error (microradians)",
    "rms_angular_error_urad": "RMS pointing error (microradians)",
    "lock_retention_pct": "Percent of time in LOCKED state",
    "avg_acquisition_time_s": "Mean time from LOST to re-LOCK (seconds)",
    "avg_processing_time_ms": "Mean per-frame processing time (ms)",
    "max_processing_time_ms": "Peak per-frame processing time (ms)",
    "reacquisition_count": "Number of re-acquisition events",
    "active_detector": "classical | ai (hybrid path when AI selected)",
}
