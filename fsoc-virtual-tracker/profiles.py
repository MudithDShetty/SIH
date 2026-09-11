"""SIH26169 profile presets: physics sandbox vs PS compliance table.

Default launch remains Physics (current BeamLock behaviour).
Use ``--profile ps`` for Parameters-table alignment without deleting physics mode.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


DEG4_URAD = 4.0 * math.pi / 180.0 * 1_000_000.0
DEG_TO_URAD = math.pi / 180.0 * 1_000_000.0


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    screen_width: int
    screen_height: int
    fov_width: int
    fov_height: int
    fov_horizontal_urad: float
    max_slew_deg_s: float
    fps: int
    square_beacon: bool
    beacon_half_size_px: int
    label: str


PROFILE_PHYSICS = RuntimeProfile(
    name="physics",
    screen_width=1280,
    screen_height=720,
    fov_width=400,
    fov_height=300,
    fov_horizontal_urad=2500.0,
    max_slew_deg_s=0.0,
    fps=60,
    square_beacon=False,
    beacon_half_size_px=4,
    label="Physics (IZN-1 class FOV)",
)

PROFILE_PS = RuntimeProfile(
    name="ps",
    screen_width=2000,
    screen_height=2000,
    fov_width=640,
    fov_height=480,
    fov_horizontal_urad=DEG4_URAD,
    max_slew_deg_s=5.0,
    fps=30,
    square_beacon=True,
    beacon_half_size_px=5,
    label="PS Compliance (26169 table)",
)


def get_profile(name: str) -> RuntimeProfile:
    key = (name or "physics").strip().lower()
    if key in {"ps", "compliance", "sih", "26169"}:
        return PROFILE_PS
    return PROFILE_PHYSICS


def slew_px_s_for_profile(profile: RuntimeProfile) -> float:
    """Convert PS °/s into px/s at the profile IFOV (helps ≤10 px tracking)."""
    if profile.max_slew_deg_s <= 0.0:
        return 90.0
    ifov = profile.fov_horizontal_urad / max(profile.fov_width, 1)
    urad_s = profile.max_slew_deg_s * DEG_TO_URAD
    return urad_s / max(ifov, 1e-9)
