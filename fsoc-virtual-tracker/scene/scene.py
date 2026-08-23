import math
import random

import pygame

TRAJECTORY_LINEAR = "linear"
TRAJECTORY_CIRCULAR = "circular"
TRAJECTORY_RANDOM_WALK = "random_walk"

TARGET_RADIUS = 4
TARGET_COLOR = (255, 235, 160)
BACKGROUND_COLOR = (8, 10, 22)


class Target:
    def __init__(
        self,
        x: float,
        y: float,
        trajectory: str = TRAJECTORY_CIRCULAR,
        speed: float = 120.0,
        *,
        center_x: float | None = None,
        center_y: float | None = None,
        radius: float = 150.0,
        angular_speed: float | None = None,
        direction: tuple[float, float] = (1.0, 0.3),
        screen_width: int = 1280,
        screen_height: int = 720,
        random_walk_sigma: float = 1.0,
    ) -> None:
        self.x = x
        self.y = y
        self.trajectory = trajectory
        self.speed = speed
        self.center_x = center_x if center_x is not None else screen_width / 2
        self.center_y = center_y if center_y is not None else screen_height / 2
        self.radius = radius
        self.angular_speed = (
            angular_speed if angular_speed is not None else speed / max(radius, 1.0)
        )
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.random_walk_sigma = random_walk_sigma

        dx, dy = direction
        length = math.hypot(dx, dy) or 1.0
        self.vx = dx / length
        self.vy = dy / length

        self.angle = math.atan2(y - self.center_y, x - self.center_x)

    def set_trajectory(self, trajectory: str) -> None:
        if trajectory == TRAJECTORY_CIRCULAR:
            self.angle = math.atan2(self.y - self.center_y, self.x - self.center_x)
            dist = math.hypot(self.x - self.center_x, self.y - self.center_y)
            if dist > 1.0:
                self.radius = dist
            self.angular_speed = self.speed / max(self.radius, 1.0)
        elif trajectory == TRAJECTORY_LINEAR:
            angle = random.uniform(0, 2 * math.pi)
            self.vx = math.cos(angle)
            self.vy = math.sin(angle)
        self.trajectory = trajectory

    def update(self, dt: float) -> None:
        if self.trajectory == TRAJECTORY_LINEAR:
            self._update_linear(dt)
        elif self.trajectory == TRAJECTORY_CIRCULAR:
            self._update_circular(dt)
        elif self.trajectory == TRAJECTORY_RANDOM_WALK:
            self._update_random_walk(dt)

    def _update_linear(self, dt: float) -> None:
        self.x += self.vx * self.speed * dt
        self.y += self.vy * self.speed * dt

    def _update_circular(self, dt: float) -> None:
        self.angle += self.angular_speed * dt
        self.x = self.center_x + self.radius * math.cos(self.angle)
        self.y = self.center_y + self.radius * math.sin(self.angle)

    def _update_random_walk(self, dt: float) -> None:
        step_scale = self.speed * dt
        self.x += random.gauss(0.0, self.random_walk_sigma) * step_scale
        self.y += random.gauss(0.0, self.random_walk_sigma) * step_scale
        self._bounce_within_bounds()

    def _bounce_within_bounds(self) -> None:
        margin = TARGET_RADIUS
        min_x = margin
        max_x = self.screen_width - margin
        min_y = margin
        max_y = self.screen_height - margin

        if self.x < min_x:
            self.x = min_x + (min_x - self.x)
        elif self.x > max_x:
            self.x = max_x - (self.x - max_x)

        if self.y < min_y:
            self.y = min_y + (min_y - self.y)
        elif self.y > max_y:
            self.y = max_y - (self.y - max_y)

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.circle(
            surface,
            TARGET_COLOR,
            (int(round(self.x)), int(round(self.y))),
            TARGET_RADIUS,
        )


class Scene:
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        targets: list[Target] | None = None,
        background_color: tuple[int, int, int] = BACKGROUND_COLOR,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.targets = list(targets) if targets is not None else []
        self.background_color = background_color

    def render(self, surface: pygame.Surface) -> None:
        surface.fill(self.background_color)
        for target in self.targets:
            target.draw(surface)
