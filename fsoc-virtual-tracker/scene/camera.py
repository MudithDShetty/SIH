import math

import pygame

from scene.scene import BACKGROUND_COLOR

# ESA IZN-1 ground station acquisition FOV ~2.5 mrad (public spec).
# Maps pixel error in the coarse camera to an angular error estimate.
COARSE_FOV_HORIZONTAL_URAD = 2500.0


class VirtualCamera:
    def __init__(
        self,
        x: float,
        y: float,
        fov_width: int = 400,
        fov_height: int = 300,
        max_slew_rate: float = 90.0,
    ) -> None:
        self.x = x
        self.y = y
        self.fov_width = fov_width
        self.fov_height = fov_height
        self.max_slew_rate = max_slew_rate

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

    def point_towards(self, target_x: float, target_y: float, dt: float) -> None:
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.hypot(dx, dy)
        if distance == 0.0:
            return

        max_step = self.max_slew_rate * dt
        if distance <= max_step:
            self.x = target_x
            self.y = target_y
        else:
            scale = max_step / distance
            self.x += dx * scale
            self.y += dy * scale

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
        """Convert scene-plane pixel error to angular error (µrad) via coarse FOV scale."""
        reference = min(self.fov_width, self.fov_height)
        return (pixel_error / max(reference, 1.0)) * COARSE_FOV_HORIZONTAL_URAD
