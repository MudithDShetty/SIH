from dataclasses import dataclass, field
from typing import Any

from physics.link_budget import LinkParams


@dataclass
class Config:
    screen_width: int = 1280
    screen_height: int = 720
    fps: int = 60
    target_defaults: dict[str, Any] = field(default_factory=dict)
    # Default optical link (976 nm acquisition beacon class).
    link_params: LinkParams = field(default_factory=LinkParams)
