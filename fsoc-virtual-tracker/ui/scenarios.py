"""Named disturbance presets for SIH demo scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from scene.scene import TRAJECTORY_CIRCULAR, TRAJECTORY_LINEAR, TRAJECTORY_RANDOM_WALK

SCENARIO_CALM = "calm"
SCENARIO_UAV = "uav"
SCENARIO_STRESS = "stress"


@dataclass(frozen=True)
class ScenarioPreset:
    label: str
    scenario_id: str
    turbulence: float
    vibration: float
    sensor_noise: float
    slew_rate: float
    trajectory: str
    description: str


PRESETS: dict[str, ScenarioPreset] = {
    SCENARIO_CALM: ScenarioPreset(
        label="Calm",
        scenario_id=SCENARIO_CALM,
        turbulence=0.0,
        vibration=0.0,
        sensor_noise=0.05,
        slew_rate=90.0,
        trajectory=TRAJECTORY_CIRCULAR,
        description="Clear sky baseline — low Cn2, no platform jitter.",
    ),
    SCENARIO_UAV: ScenarioPreset(
        label="UAV",
        scenario_id=SCENARIO_UAV,
        turbulence=4.0,
        vibration=8.0,
        sensor_noise=0.2,
        slew_rate=90.0,
        trajectory=TRAJECTORY_CIRCULAR,
        description="Moderate Cn2 + tip/tilt (mobile-platform benchmark).",
    ),
    SCENARIO_STRESS: ScenarioPreset(
        label="Stress",
        scenario_id=SCENARIO_STRESS,
        turbulence=7.0,
        vibration=15.0,
        sensor_noise=0.35,
        slew_rate=120.0,
        trajectory=TRAJECTORY_RANDOM_WALK,
        description="Strong Cn2, scintillation, and jitter — acquisition stress.",
    ),
}

PRESET_ORDER = (SCENARIO_CALM, SCENARIO_UAV, SCENARIO_STRESS)
