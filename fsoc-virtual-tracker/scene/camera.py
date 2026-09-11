import math

import pygame

from scene.scene import BACKGROUND_COLOR

# ESA IZN-1 ground station acquisition FOV ~2.5 mrad (public spec).
COARSE_FOV_HORIZONTAL_URAD = 2500.0

# Default gimbal plant limits (software model, not flight hardware).
DEFAULT_MAX_SLEW_URAD_S = 562.5  # 90 px/s @ 6.25 µrad/px
DEFAULT_MAX_ACCEL_URAD_S2 = 4000.0


class VirtualCamera:
    """Coarse PAT camera with AZ/EL plant, angular FOV, and IFOV.

    Scene coordinates remain pixels for the 2D sandbox. Azimuth / elevation
    are µrad offsets from a scene origin (default: screen center), mapped via
    true IFOV = FOV_urad / N_pix. Slew uses rate + acceleration limits.
    """

    def __init__(
        self,
        x: float,
        y: float,
        fov_width: int = 400,
        fov_height: int = 300,
        max_slew_rate: float = 90.0,
        fov_horizontal_urad: float = COARSE_FOV_HORIZONTAL_URAD,
        *,
        origin_x: float | None = None,
        origin_y: float | None = None,
        max_accel_urad_s2: float = DEFAULT_MAX_ACCEL_URAD_S2,
    ) -> None:
        self.x = x
        self.y = y
        self.fov_width = fov_width
        self.fov_height = fov_height
        self.max_slew_rate = max_slew_rate  # px/s (UI); see max_slew_rate_urad_s
        self.fov_horizontal_urad = fov_horizontal_urad
        self.origin_x = float(origin_x if origin_x is not None else x)
        self.origin_y = float(origin_y if origin_y is not None else y)
        self.max_accel_urad_s2 = max_accel_urad_s2
        self._az_rate_urad_s = 0.0
        self._el_rate_urad_s = 0.0

    @property
    def ifov_urad(self) -> float:
        """Instantaneous field of view per pixel (µrad/px) along width."""
        return self.fov_horizontal_urad / max(self.fov_width, 1)

    @property
    def fov_vertical_urad(self) -> float:
        return self.ifov_urad * self.fov_height

    @property
    def az_urad(self) -> float:
        """Azimuth (horizontal) pointing offset from origin, µrad."""
        return (self.x - self.origin_x) * self.ifov_urad

    @property
    def el_urad(self) -> float:
        """Elevation (vertical) pointing offset from origin, µrad."""
        return (self.y - self.origin_y) * self.ifov_urad

    @property
    def max_slew_rate_urad_s(self) -> float:
        return self.max_slew_rate * self.ifov_urad

    @max_slew_rate_urad_s.setter
    def max_slew_rate_urad_s(self, value: float) -> None:
        self.max_slew_rate = float(value) / max(self.ifov_urad, 1e-9)

    def urad_to_px(self, urad: float) -> float:
        return urad / max(self.ifov_urad, 1e-9)

    def px_to_urad(self, pixels: float) -> float:
        return pixels * self.ifov_urad

    def scene_to_azel(self, scene_x: float, scene_y: float) -> tuple[float, float]:
        return (
            (scene_x - self.origin_x) * self.ifov_urad,
            (scene_y - self.origin_y) * self.ifov_urad,
        )

    def azel_to_scene(self, az_urad: float, el_urad: float) -> tuple[float, float]:
        return (
            self.origin_x + az_urad / max(self.ifov_urad, 1e-9),
            self.origin_y + el_urad / max(self.ifov_urad, 1e-9),
        )

    def residual_azel_urad(
        self, target_x: float, target_y: float
    ) -> tuple[float, float]:
        taz, tel = self.scene_to_azel(target_x, target_y)
        return taz - self.az_urad, tel - self.el_urad

    def get_fov_rect(
        self,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> pygame.Rect:
        center_x = self.x + offset_x
        center_y = self.y + offset_y
        return pygame.Rect(
            int(round(center_x - self.fov_width / 2)),
            int(round(center_y - self.fov_height / 2)),
            self.fov_width,
            self.fov_height,
        )

    def point_towards(
        self,
        target_x: float,
        target_y: float,
        dt: float,
        *,
        slew_multiplier: float = 1.0,
    ) -> None:
        """Rate- and acceleration-limited slew toward a scene-plane target."""
        dt = max(dt, 1e-6)
        daz, del_ = self.residual_azel_urad(target_x, target_y)
        err = math.hypot(daz, del_)
        if err < 1e-6:
            self._az_rate_urad_s = 0.0
            self._el_rate_urad_s = 0.0
            return

        max_rate = self.max_slew_rate_urad_s * max(slew_multiplier, 0.1)
        # Desired rate: proportional, saturated.
        desired_rate = min(err / dt, max_rate)
        ux, uy = daz / err, del_ / err
        desired_az_rate = ux * desired_rate
        desired_el_rate = uy * desired_rate

        max_drate = self.max_accel_urad_s2 * dt
        self._az_rate_urad_s = _clamp_rate(
            self._az_rate_urad_s, desired_az_rate, max_drate, max_rate
        )
        self._el_rate_urad_s = _clamp_rate(
            self._el_rate_urad_s, desired_el_rate, max_drate, max_rate
        )

        self.x += self.urad_to_px(self._az_rate_urad_s * dt)
        self.y += self.urad_to_px(self._el_rate_urad_s * dt)

        # Snap if within one integration step of the target.
        if err <= max_rate * dt:
            self.x = target_x
            self.y = target_y
            self._az_rate_urad_s = 0.0
            self._el_rate_urad_s = 0.0

    def is_visible(
        self,
        x: float,
        y: float,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> bool:
        center_x = self.x + offset_x
        center_y = self.y + offset_y
        half_w = self.fov_width / 2
        half_h = self.fov_height / 2
        return (
            center_x - half_w <= x <= center_x + half_w
            and center_y - half_h <= y <= center_y + half_h
        )

    def get_view(
        self,
        scene_surface: pygame.Surface,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> pygame.Surface:
        view = pygame.Surface((self.fov_width, self.fov_height))
        view.fill(BACKGROUND_COLOR)

        source_rect = self.get_fov_rect(offset_x, offset_y)
        scene_rect = scene_surface.get_rect()
        visible_rect = source_rect.clip(scene_rect)
        if visible_rect.width <= 0 or visible_rect.height <= 0:
            return view

        dest_x = visible_rect.x - source_rect.x
        dest_y = visible_rect.y - source_rect.y
        view.blit(scene_surface, (dest_x, dest_y), visible_rect)
        return view

    def local_to_scene(
        self,
        local_x: float,
        local_y: float,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> tuple[float, float]:
        fov_rect = self.get_fov_rect(offset_x, offset_y)
        return fov_rect.x + local_x, fov_rect.y + local_y

    def scene_to_local(
        self,
        scene_x: float,
        scene_y: float,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> tuple[float, float]:
        fov_rect = self.get_fov_rect(offset_x, offset_y)
        return scene_x - fov_rect.x, scene_y - fov_rect.y

    def pixel_error_to_urad(self, pixel_error: float) -> float:
        """Convert scene-plane pixel error to angular error via true IFOV."""
        return self.px_to_urad(pixel_error)


def _clamp_rate(
    current: float, desired: float, max_delta: float, max_abs: float
) -> float:
    delta = desired - current
    if abs(delta) > max_delta:
        delta = math.copysign(max_delta, delta)
    value = current + delta
    if abs(value) > max_abs:
        value = math.copysign(max_abs, value)
    return value
