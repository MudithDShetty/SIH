import random

import cv2
import numpy as np
import pygame


def _surface_to_bgr(surface: pygame.Surface) -> np.ndarray:
    rgb = pygame.surfarray.array3d(surface)
    bgr = np.transpose(rgb, (1, 0, 2))[:, :, ::-1].copy()
    return bgr


def _bgr_to_surface(image: np.ndarray) -> pygame.Surface:
    rgb = image[:, :, ::-1]
    transposed = np.transpose(rgb, (1, 0, 2))
    return pygame.surfarray.make_surface(transposed)


class TurbulenceModel:
    """Fast image-domain turbulence placeholder.

    A low-resolution random displacement field is smoothed and upsampled, then
    applied with cv2.remap. This is a stand-in for a physically accurate
    split-step / phase-screen propagation model.

  strength scales displacement magnitude in pixels and is an approximate visual
    proxy for optical severity: higher strength ~ stronger turbulence (larger
    Cn^2, smaller Fried parameter r0). The mapping is qualitative only.
    """

    GRID_WIDTH = 8
    GRID_HEIGHT = 6
    MAX_STRENGTH = 10.0

    def __init__(self, strength: float = 0.0) -> None:
        self.strength = float(np.clip(strength, 0.0, self.MAX_STRENGTH))

    def adjust_strength(self, delta: float) -> float:
        self.strength = float(np.clip(self.strength + delta, 0.0, self.MAX_STRENGTH))
        return self.strength

    def apply(self, surface: pygame.Surface) -> pygame.Surface:
        if self.strength <= 0.0:
            return surface

        width, height = surface.get_size()
        if width == 0 or height == 0:
            return surface

        displacement_x = np.random.randn(self.GRID_HEIGHT, self.GRID_WIDTH).astype(
            np.float32
        )
        displacement_y = np.random.randn(self.GRID_HEIGHT, self.GRID_WIDTH).astype(
            np.float32
        )
        displacement_x = cv2.GaussianBlur(displacement_x, (0, 0), sigmaX=1.2)
        displacement_y = cv2.GaussianBlur(displacement_y, (0, 0), sigmaX=1.2)

        displacement_x = cv2.resize(
            displacement_x, (width, height), interpolation=cv2.INTER_CUBIC
        )
        displacement_y = cv2.resize(
            displacement_y, (width, height), interpolation=cv2.INTER_CUBIC
        )

        # strength=1.0 -> about +/-1 px RMS warp; scale linearly from there.
        displacement_x *= self.strength
        displacement_y *= self.strength

        map_x, map_y = np.meshgrid(
            np.arange(width, dtype=np.float32),
            np.arange(height, dtype=np.float32),
        )
        map_x = map_x + displacement_x
        map_y = map_y + displacement_y

        image = _surface_to_bgr(surface)
        warped = cv2.remap(
            image,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT101,
        )
        return _bgr_to_surface(warped)


class VibrationModel:
    """Platform jitter via a simple AR(1) filtered-noise model."""

    MAX_AMPLITUDE = 50.0

    def __init__(self, amplitude: float = 0.0, correlation: float = 0.92) -> None:
        self.amplitude = float(np.clip(amplitude, 0.0, self.MAX_AMPLITUDE))
        self.correlation = correlation
        self.offset_x = 0.0
        self.offset_y = 0.0

    def adjust_amplitude(self, delta: float) -> float:
        self.amplitude = float(np.clip(self.amplitude + delta, 0.0, self.MAX_AMPLITUDE))
        return self.amplitude

    def update(self, dt: float) -> tuple[float, float]:
        if self.amplitude <= 0.0:
            self.offset_x = 0.0
            self.offset_y = 0.0
            return self.offset_x, self.offset_y

        alpha = self.correlation ** max(dt * 60.0, 1e-6)
        innovation_scale = self.amplitude * np.sqrt(max(1.0 - alpha * alpha, 0.0))

        self.offset_x = alpha * self.offset_x + innovation_scale * random.gauss(0.0, 1.0)
        self.offset_y = alpha * self.offset_y + innovation_scale * random.gauss(0.0, 1.0)
        return self.offset_x, self.offset_y


class SensorNoiseModel:
    """Gaussian read noise plus mild contrast/brightness loss."""

    MAX_NOISE_LEVEL = 1.0

    def __init__(self, noise_level: float = 0.0) -> None:
        self.noise_level = float(np.clip(noise_level, 0.0, self.MAX_NOISE_LEVEL))

    def adjust_noise_level(self, delta: float) -> float:
        self.noise_level = float(np.clip(self.noise_level + delta, 0.0, self.MAX_NOISE_LEVEL))
        return self.noise_level

    def apply(self, surface: pygame.Surface) -> pygame.Surface:
        if self.noise_level <= 0.0:
            return surface

        image = _surface_to_bgr(surface).astype(np.float32)
        mean = image.mean(axis=(0, 1), keepdims=True)
        contrast_scale = 1.0 - 0.25 * self.noise_level
        brightness_shift = -8.0 * self.noise_level
        image = (image - mean) * contrast_scale + mean + brightness_shift

        sigma = 3.0 + 30.0 * self.noise_level
        image += np.random.normal(0.0, sigma, image.shape).astype(np.float32)
        image = np.clip(image, 0.0, 255.0).astype(np.uint8)
        return _bgr_to_surface(image)
