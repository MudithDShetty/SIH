"""SIH26169 weather + named sensor-noise helpers (additive; physics mode unchanged)."""

from __future__ import annotations

from dataclasses import dataclass


NOISE_GAUSSIAN = "gaussian"
NOISE_SALT_PEPPER = "salt_pepper"
NOISE_POISSON = "poisson"
NOISE_LEGACY = "legacy"  # existing BeamLock mix

NOISE_MODES = (
    NOISE_LEGACY,
    NOISE_GAUSSIAN,
    NOISE_SALT_PEPPER,
    NOISE_POISSON,
)


@dataclass(frozen=True)
class WeatherPreset:
    name: str
    contrast: float
    brightness: float
    turb_boost: float
    label: str


WEATHER_PRESETS: dict[str, WeatherPreset] = {
    "clear": WeatherPreset("clear", 1.0, 0.0, 0.0, "Clear"),
    "haze": WeatherPreset("haze", 0.78, -12.0, 1.0, "Haze"),
    "fog": WeatherPreset("fog", 0.55, -25.0, 1.5, "Fog"),
    "rain": WeatherPreset("rain", 0.7, -18.0, 2.0, "Rain"),
    "low_light": WeatherPreset("low_light", 0.85, -40.0, 0.5, "Low light"),
}

WEATHER_ORDER = ("clear", "haze", "fog", "rain", "low_light")
