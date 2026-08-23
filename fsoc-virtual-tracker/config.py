from dataclasses import dataclass, field
from typing import Any


@dataclass
class Config:
    screen_width: int = 1280
    screen_height: int = 720
    fps: int = 60
    target_defaults: dict[str, Any] = field(default_factory=dict)
