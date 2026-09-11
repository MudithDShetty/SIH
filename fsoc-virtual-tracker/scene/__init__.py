"""Scene package: virtual world, beacons, and AZ/EL camera plant.

Modules
-------
scene
    Sky render, beacon trajectories (linear/circular/random/figure-8), clutter.
camera
    FOV crop, rate-limited AZ/EL pointing, true IFOV (µrad/px).
"""

from scene.camera import VirtualCamera
from scene.scene import (
    BACKGROUND_COLOR,
    TRAJECTORY_CIRCULAR,
    TRAJECTORY_FIGURE8,
    TRAJECTORY_LINEAR,
    TRAJECTORY_RANDOM_WALK,
    ClutterField,
    Scene,
    Target,
)

__all__ = [
    "BACKGROUND_COLOR",
    "TRAJECTORY_CIRCULAR",
    "TRAJECTORY_FIGURE8",
    "TRAJECTORY_LINEAR",
    "TRAJECTORY_RANDOM_WALK",
    "ClutterField",
    "Scene",
    "Target",
    "VirtualCamera",
]
