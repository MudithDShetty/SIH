"""Headless physics preview capture for Calm / UAV / Stress scenarios."""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# Project root (script lives in logs/preview/)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

from config import Config
from disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
from physics import OpticalLink
from scene import Scene, Target, VirtualCamera, TRAJECTORY_CIRCULAR

FOV_OUTLINE_COLOR = (72, 220, 140)
HUD_COLOR = (210, 220, 235)
FRAMES = 90
DT = 1.0 / 60.0

SCENARIOS = (
    ("calm", 0.0, 0.0, 0.05, 90.0),
    ("uav", 4.0, 8.0, 0.2, 90.0),
    ("stress", 7.0, 15.0, 0.35, 120.0),
)

OUT_DIR = Path("logs/preview")


def run_scenario(
    name: str,
    turb: float,
    vib: float,
    noise: float,
    slew: float,
) -> tuple[Path, dict[str, float]]:
    config = Config()
    width, height = config.screen_width, config.screen_height

    pygame.init()
    # Dummy driver still needs a display surface for blit/save.
    screen = pygame.display.set_mode((width, height))
    font = pygame.font.SysFont(None, 22)
    scene_surface = pygame.Surface((width, height))

    beacon = Target(
        x=width / 2 + 150,
        y=height / 2,
        trajectory=TRAJECTORY_CIRCULAR,
        speed=120.0,
        center_x=width / 2,
        center_y=height / 2,
        radius=150.0,
        screen_width=width,
        screen_height=height,
    )
    scene = Scene(width, height, targets=[beacon])
    camera = VirtualCamera(
        x=width / 2,
        y=height / 2,
        fov_width=400,
        fov_height=300,
        max_slew_rate=slew,
    )
    turbulence = TurbulenceModel(strength=turb)
    vibration = VibrationModel(amplitude=vib)
    sensor_noise = SensorNoiseModel(noise_level=noise)
    optical_link = OpticalLink(config.link_params)

    left_w = width // 2
    right_w = width - left_w
    overview_scale = left_w / width
    overview_size = (left_w, int(round(height * overview_scale)))
    overview_y = (height - overview_size[1]) // 2

    atm = turbulence.last_state
    link = optical_link.compute(residual_urad=0.0, scintillation=1.0)
    wander_x_px = wander_y_px = 0.0
    vibration_offset_x = vibration_offset_y = 0.0

    for _ in range(FRAMES):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                break

        beacon.update(DT)
        vibration_offset_x, vibration_offset_y = vibration.update(DT)
        atm = turbulence.update(DT)
        wander_x_px, wander_y_px = turbulence.wander_offset_px(camera.ifov_urad)

        boresight_err_px = math.hypot(camera.x - beacon.x, camera.y - beacon.y)
        boresight_urad = camera.px_to_urad(boresight_err_px)
        link = optical_link.compute(
            residual_urad=boresight_urad,
            scintillation=atm.scintillation,
        )
        beacon.set_optical_appearance(
            draw_x=beacon.x + wander_x_px,
            draw_y=beacon.y + wander_y_px,
            spot_sigma_px=optical_link.spot_sigma_px(camera.ifov_urad),
            intensity=atm.scintillation * (0.35 + 0.65 * link.pointing_loss),
        )

        scene.render(scene_surface)
        camera_view = camera.get_view(
            scene_surface, vibration_offset_x, vibration_offset_y
        )
        camera_view = turbulence.apply(camera_view)
        camera_view = sensor_noise.apply(camera_view)

        # Ideal follow (physics preview, no detector lag).
        camera.point_towards(beacon.x, beacon.y, DT)

        screen.fill((0, 0, 0))
        overview = pygame.transform.smoothscale(scene_surface, overview_size)
        screen.blit(overview, (0, overview_y))

        fov_rect = camera.get_fov_rect(vibration_offset_x, vibration_offset_y)
        overlay_rect = pygame.Rect(
            int(round(fov_rect.x * overview_scale)),
            int(round(fov_rect.y * overview_scale)) + overview_y,
            int(round(fov_rect.width * overview_scale)),
            int(round(fov_rect.height * overview_scale)),
        )
        pygame.draw.rect(screen, FOV_OUTLINE_COLOR, overlay_rect, 2)

        camera_display = pygame.transform.smoothscale(
            camera_view, (right_w, height)
        )
        screen.blit(camera_display, (left_w, 0))

        r0_cm = atm.r0_m * 100.0
        wander_mag_px = math.hypot(wander_x_px, wander_y_px)
        wander_mag_urad = math.hypot(atm.wander_x_urad, atm.wander_y_urad)
        hud_lines = [
            f"Scenario: {name.upper()}  frames={FRAMES}",
            f"turb={turb:.1f}  vib={vib:.1f}  noise={noise:.2f}",
            f"Cn2: {atm.cn2:.2e}  r0: {r0_cm:.1f} cm  I: {atm.scintillation:.2f}",
            f"SNR: {link.snr_db:.1f} dB  pointing: {link.pointing_loss:.3f}",
            f"IFOV: {camera.ifov_urad:.2f} urad/px",
            (
                f"wander: {wander_mag_px:.2f} px "
                f"({wander_mag_urad:.1f} urad)  "
                f"dx={wander_x_px:.2f} dy={wander_y_px:.2f}"
            ),
            f"camera: ({camera.x:.1f}, {camera.y:.1f})  beacon: ({beacon.x:.1f}, {beacon.y:.1f})",
        ]
        for index, line in enumerate(hud_lines):
            text_surface = font.render(line, True, HUD_COLOR)
            screen.blit(text_surface, (8, 8 + index * 20))

        pygame.display.flip()

    out_path = OUT_DIR / f"physics_{name}.png"
    pygame.image.save(screen, str(out_path))
    pygame.quit()

    metrics = {
        "cn2": atm.cn2,
        "r0_cm": atm.r0_m * 100.0,
        "I": atm.scintillation,
        "snr_db": link.snr_db,
        "ifov_urad": camera.ifov_urad,
        "wander_px": math.hypot(wander_x_px, wander_y_px),
        "wander_urad": math.hypot(atm.wander_x_urad, atm.wander_y_urad),
        "pointing_loss": link.pointing_loss,
    }
    return out_path, metrics


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, turb, vib, noise, slew in SCENARIOS:
        path, m = run_scenario(name, turb, vib, noise, slew)
        print(f"[{name}] saved {path.resolve()}")
        print(
            f"  Cn2={m['cn2']:.3e}  r0={m['r0_cm']:.2f} cm  I={m['I']:.3f}  "
            f"SNR={m['snr_db']:.2f} dB  IFOV={m['ifov_urad']:.3f} urad/px  "
            f"wander={m['wander_px']:.3f} px ({m['wander_urad']:.2f} urad)  "
            f"pointing_loss={m['pointing_loss']:.3f}"
        )


if __name__ == "__main__":
    main()

