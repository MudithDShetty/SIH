import math
import random

import pygame

TRAJECTORY_LINEAR = "linear"
TRAJECTORY_CIRCULAR = "circular"
TRAJECTORY_RANDOM_WALK = "random_walk"
TRAJECTORY_FIGURE8 = "figure8"

TARGET_RADIUS = 4
TARGET_COLOR = (255, 235, 160)
BACKGROUND_COLOR = (8, 10, 22)


def _clamp_byte(value: float) -> int:
    return int(max(0, min(255, round(value))))


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

        # Optical appearance (updated each frame from link / channel).
        self.draw_x = x
        self.draw_y = y
        self.spot_sigma_px = float(TARGET_RADIUS)
        self.intensity = 1.0
        self.base_color = TARGET_COLOR
        # SIH26169 optional square beacon (default remains Gaussian blob).
        self.render_mode = "gaussian"  # or "square"
        self.square_half_size_px = 5
        self._figure8_phase = 0.0

    def set_optical_appearance(
        self,
        *,
        draw_x: float | None = None,
        draw_y: float | None = None,
        spot_sigma_px: float | None = None,
        intensity: float | None = None,
    ) -> None:
        if draw_x is not None:
            self.draw_x = draw_x
        if draw_y is not None:
            self.draw_y = draw_y
        if spot_sigma_px is not None:
            self.spot_sigma_px = max(1.0, float(spot_sigma_px))
        if intensity is not None:
            self.intensity = max(0.0, float(intensity))

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
        elif trajectory == TRAJECTORY_FIGURE8:
            self._figure8_phase = 0.0
        self.trajectory = trajectory

    def update(self, dt: float) -> None:
        if self.trajectory == TRAJECTORY_LINEAR:
            self._update_linear(dt)
        elif self.trajectory == TRAJECTORY_CIRCULAR:
            self._update_circular(dt)
        elif self.trajectory == TRAJECTORY_RANDOM_WALK:
            self._update_random_walk(dt)
        elif self.trajectory == TRAJECTORY_FIGURE8:
            self._update_figure8(dt)
        # Default appearance follows geometric LOS until channel updates it.
        self.draw_x = self.x
        self.draw_y = self.y

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

    def _update_figure8(self, dt: float) -> None:
        """Lemniscate of Bernoulli (figure-8), SIH26169 mandatory motion set."""
        self._figure8_phase += (self.speed / max(self.radius, 1.0)) * dt
        a = max(self.radius, 40.0)
        s = math.sin(self._figure8_phase)
        c = math.cos(self._figure8_phase)
        denom = 1.0 + s * s
        self.x = self.center_x + a * c / denom
        self.y = self.center_y + a * s * c / denom

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
        """Draw beacon footprint (Gaussian default, or SIH square patch)."""
        cx = int(round(self.draw_x))
        cy = int(round(self.draw_y))
        intensity = max(0.0, min(self.intensity, 3.0))

        if self.render_mode == "square":
            half = max(2, int(self.square_half_size_px))
            amp = min(1.0, intensity)
            color = (
                _clamp_byte(255 * amp),
                _clamp_byte(245 * amp),
                _clamp_byte(220 * amp),
            )
            rect = pygame.Rect(cx - half, cy - half, 2 * half, 2 * half)
            pygame.draw.rect(surface, color, rect)
            return

        sigma = self.spot_sigma_px
        radius = max(2, int(math.ceil(3.0 * sigma)))

        # Layered discs approximate a Gaussian irradiance profile cheaply.
        for ring in range(radius, 0, -1):
            t = ring / max(radius, 1)
            # Gaussian falloff
            amp = math.exp(-0.5 * (ring / max(sigma, 1e-6)) ** 2) * intensity
            color = (
                _clamp_byte(self.base_color[0] * amp),
                _clamp_byte(self.base_color[1] * amp),
                _clamp_byte(self.base_color[2] * amp * (0.85 + 0.15 * t)),
            )
            if color[0] + color[1] + color[2] < 8:
                continue
            pygame.draw.circle(surface, color, (cx, cy), ring)

        core = (
            _clamp_byte(255 * min(1.0, intensity)),
            _clamp_byte(245 * min(1.0, intensity)),
            _clamp_byte(200 * min(1.0, intensity)),
        )
        pygame.draw.circle(surface, core, (cx, cy), max(1, int(round(0.45 * sigma))))


class ClutterField:
    """Procedural star / glint clutter for detector ROC stress tests."""

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        *,
        star_count: int = 40,
        glint_count: int = 6,
        seed: int = 0,
    ) -> None:
        rng = random.Random(seed)
        self.stars = [
            (
                rng.uniform(0, screen_width),
                rng.uniform(0, screen_height),
                rng.randint(1, 2),
                rng.randint(140, 230),
            )
            for _ in range(max(0, star_count))
        ]
        self.glints = [
            (
                rng.uniform(40, screen_width - 40),
                rng.uniform(40, screen_height - 40),
                rng.uniform(2.0, 5.0),
                rng.uniform(0.35, 0.85),
            )
            for _ in range(max(0, glint_count))
        ]

    def draw(self, surface: pygame.Surface) -> None:
        for x, y, radius, brightness in self.stars:
            color = (brightness, brightness, min(255, brightness + 20))
            pygame.draw.circle(surface, color, (int(x), int(y)), radius)
        for x, y, sigma, intensity in self.glints:
            cx, cy = int(x), int(y)
            radius = max(2, int(math.ceil(2.5 * sigma)))
            for ring in range(radius, 0, -1):
                amp = math.exp(-0.5 * (ring / max(sigma, 1e-6)) ** 2) * intensity
                color = (
                    _clamp_byte(220 * amp),
                    _clamp_byte(200 * amp),
                    _clamp_byte(160 * amp),
                )
                if color[0] + color[1] + color[2] < 10:
                    continue
                pygame.draw.circle(surface, color, (cx, cy), ring)


class Scene:
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        targets: list[Target] | None = None,
        background_color: tuple[int, int, int] = BACKGROUND_COLOR,
        clutter: ClutterField | None = None,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.targets = list(targets) if targets is not None else []
        self.background_color = background_color
        self.clutter = clutter

    def enable_clutter(
        self,
        *,
        star_count: int = 40,
        glint_count: int = 6,
        seed: int = 0,
    ) -> None:
        self.clutter = ClutterField(
            self.screen_width,
            self.screen_height,
            star_count=star_count,
            glint_count=glint_count,
            seed=seed,
        )

    def render(self, surface: pygame.Surface) -> None:
        surface.fill(self.background_color)
        if self.clutter is not None:
            self.clutter.draw(surface)
        for target in self.targets:
            target.draw(surface)
