#!/usr/bin/env python3
"""Record an SIH demo MP4 from the real BeamLock simulation stack (headless).

Segments: title → Calm → UAV → Stress → force lock-loss / raster re-acq →
AI+fusion UAV → outro. Uses the same scene/physics/detector/Kalman/control
path as run_comparison / main (SDL dummy display).
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from config import Config
from control import FinePointingController, ReacquisitionController
from detector.classical_detector import ClassicalDetector
from disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
from metrics import LinkReadinessScore
from physics import OpticalLink
from scene import Scene, Target, VirtualCamera, TRAJECTORY_CIRCULAR, TRAJECTORY_RANDOM_WALK
from tracker import BeaconTracker, TRACKING_LOCKED, TRACKING_LOST
from ui.scenarios import PRESETS, SCENARIO_CALM, SCENARIO_STRESS, SCENARIO_UAV

from main import (
    DETECTOR_BLIND_FRAMES,
    MAX_ACQ_SLEW_MULTIPLIER,
    draw_crosshair,
    draw_kalman_marker,
    draw_link_readiness_gauge,
    draw_marker_if_in_view,
    draw_quad_overlay,
    draw_search_overlay,
    is_plausible_reacq_detection,
    surface_to_bgr,
)

FOV_OUTLINE_COLOR = (72, 220, 140)
TITLE_BG = (8, 14, 24)
TITLE_FG = (230, 238, 248)
ACCENT = (126, 200, 227)


@dataclass
class Segment:
    label: str
    scenario: str | None
    detector: str  # classical | ai | none
    duration_s: float
    force_blind_at_s: float | None = None
    title_only: bool = False
    subtitle: str = ""


SEGMENTS: list[Segment] = [
    Segment(
        "BeamLock",
        None,
        "none",
        3.0,
        title_only=True,
        subtitle="SIH26169 · Team Cadets · Virtual coarse-to-fine PAT for mobile FSOC",
    ),
    Segment("Calm · Classical", SCENARIO_CALM, "classical", 7.0, subtitle="Baseline lock"),
    Segment("UAV · Classical", SCENARIO_UAV, "classical", 9.0, subtitle="Moderate Cn² + vibration"),
    Segment(
        "Stress · Classical",
        SCENARIO_STRESS,
        "classical",
        8.0,
        subtitle="Strong channel · hold / recover",
    ),
    Segment(
        "Lock loss → Raster re-acq",
        SCENARIO_STRESS,
        "classical",
        12.0,
        force_blind_at_s=1.5,
        subtitle="Forced detector blind (L) then automatic search",
    ),
    Segment(
        "UAV · AI+fusion",
        SCENARIO_UAV,
        "ai",
        10.0,
        subtitle="Denoise → YOLO + classical consensus",
    ),
    Segment(
        "BeamLock",
        None,
        "none",
        4.0,
        title_only=True,
        subtitle="Full prototype: python main.py · GitHub: MudithDShetty/SIH",
    ),
]


def seed_frame(frame_index: int, base_seed: int) -> None:
    np.random.seed(base_seed + frame_index)
    random.seed(base_seed + frame_index)


def blit_caption(screen: pygame.Surface, font: pygame.font.Font, big: pygame.font.Font, segment: Segment) -> None:
    bar = pygame.Surface((screen.get_width(), 54), pygame.SRCALPHA)
    bar.fill((0, 0, 0, 160))
    screen.blit(bar, (0, 0))
    title = big.render(segment.label, True, TITLE_FG)
    screen.blit(title, (16, 8))
    if segment.subtitle:
        sub = font.render(segment.subtitle, True, ACCENT)
        screen.blit(sub, (16, 32))


def render_title_card(
    screen: pygame.Surface,
    font: pygame.font.Font,
    big: pygame.font.Font,
    segment: Segment,
) -> None:
    screen.fill(TITLE_BG)
    title = big.render(segment.label, True, TITLE_FG)
    tr = title.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 - 24))
    screen.blit(title, tr)
    if segment.subtitle:
        # Word-wrap-ish by splitting on ·
        y = screen.get_height() // 2 + 20
        for part in segment.subtitle.split(" · "):
            line = font.render(part.strip(), True, ACCENT)
            lr = line.get_rect(center=(screen.get_width() // 2, y))
            screen.blit(line, lr)
            y += 26


def surface_to_bgr_frame(surface: pygame.Surface) -> np.ndarray:
    """RGB pygame surface → contiguous BGR uint8 for OpenCV VideoWriter."""
    rgb = pygame.surfarray.array3d(surface)
    # surfarray is (w, h, 3); OpenCV wants (h, w, 3)
    frame = np.transpose(rgb, (1, 0, 2))
    return np.ascontiguousarray(frame[:, :, ::-1])


class DemoRecorder:
    def __init__(self, fps: int, base_seed: int) -> None:
        self.fps = fps
        self.dt = 1.0 / fps
        self.base_seed = base_seed
        self.config = Config()
        self.width = self.config.screen_width
        self.height = self.config.screen_height

        pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.scene_surface = pygame.Surface((self.width, self.height))
        self.font = pygame.font.SysFont("consolas", 18)
        self.big = pygame.font.SysFont("segoeui", 36, bold=True)
        self.hud_font = pygame.font.SysFont("consolas", 20)

        self.left_w = self.width // 2
        self.right_w = self.width - self.left_w
        self.overview_scale = self.left_w / self.width
        self.overview_size = (self.left_w, int(round(self.height * self.overview_scale)))
        self.overview_y = (self.height - self.overview_size[1]) // 2

        self.classical = ClassicalDetector()
        self.hybrid = None
        self._try_load_ai()

        self.optical_link = OpticalLink(self.config.link_params)
        self.frame_counter = 0

    def _try_load_ai(self) -> None:
        weights = ROOT / "weights" / "beacon_yolov8n.pt"
        if not weights.exists():
            print("AI weights missing — AI+fusion segment will fall back to classical.")
            return
        try:
            from detector.ai_detector import AIDetector
            from detector.hybrid_detector import HybridDetector

            self.hybrid = HybridDetector(AIDetector(), self.classical)
            print("AI+fusion detector ready.")
        except Exception as exc:  # noqa: BLE001
            print(f"AI load failed ({exc}) — AI segment uses classical.")
            self.hybrid = None

    def _reset_world(self, scenario_id: str, detector_name: str) -> None:
        preset = PRESETS[scenario_id]
        traj = (
            TRAJECTORY_RANDOM_WALK
            if scenario_id == SCENARIO_STRESS
            else TRAJECTORY_CIRCULAR
        )
        self.beacon = Target(
            x=self.width / 2 + 150,
            y=self.height / 2,
            trajectory=traj,
            speed=120.0,
            center_x=self.width / 2,
            center_y=self.height / 2,
            radius=150.0,
            screen_width=self.width,
            screen_height=self.height,
        )
        self.scene = Scene(self.width, self.height, targets=[self.beacon])
        self.camera = VirtualCamera(
            x=self.width / 2,
            y=self.height / 2,
            fov_width=400,
            fov_height=300,
            max_slew_rate=preset.slew_rate,
        )
        self.turb = TurbulenceModel(strength=preset.turbulence)
        self.vib = VibrationModel(amplitude=preset.vibration)
        self.noise = SensorNoiseModel(noise_level=preset.sensor_noise)
        self.tracker = BeaconTracker(
            initial_x=self.width / 2,
            initial_y=self.height / 2,
        )
        self.reacquisition = ReacquisitionController(self.width, self.height)
        self.fine = FinePointingController()
        self.link_readiness = LinkReadinessScore(
            fov_width=self.camera.fov_width,
            fov_height=self.camera.fov_height,
        )

        use_ai = detector_name == "ai" and self.hybrid is not None
        self.active_detector = self.hybrid if use_ai else self.classical
        self.active_detector_name = "AI+fusion" if use_ai else "classical"
        self.use_ai = use_ai

        self.previous_tracking_state = TRACKING_LOST
        self.last_locked_x = self.width / 2
        self.last_locked_y = self.height / 2
        self.last_velocity_x = 0.0
        self.last_velocity_y = 0.0
        self.lost_search_time = 0.0
        self.reacquisition_count = 0
        self.detector_blind_frames = 0
        self.handoff_count = 0
        self.segment_time = 0.0

    def _step(self) -> dict:
        seed_frame(self.frame_counter, self.base_seed)
        self.frame_counter += 1
        dt = self.dt

        for target in self.scene.targets:
            target.update(dt)

        vibration_offset_x, vibration_offset_y = self.vib.update(dt)
        atm = self.turb.update(dt)
        wander_x_px, wander_y_px = self.turb.wander_offset_px(self.camera.ifov_urad)
        boresight_err_px = math.hypot(self.camera.x - self.beacon.x, self.camera.y - self.beacon.y)
        link = self.optical_link.compute(
            residual_urad=self.camera.px_to_urad(boresight_err_px),
            scintillation=atm.scintillation,
        )
        self.beacon.set_optical_appearance(
            draw_x=self.beacon.x + wander_x_px,
            draw_y=self.beacon.y + wander_y_px,
            spot_sigma_px=self.optical_link.spot_sigma_px(self.camera.ifov_urad),
            intensity=atm.scintillation * (0.35 + 0.65 * link.pointing_loss),
        )
        self.scene.render(self.scene_surface)
        camera_view = self.camera.get_view(
            self.scene_surface, vibration_offset_x, vibration_offset_y
        )
        camera_view = self.turb.apply(camera_view)
        camera_view = self.noise.apply(camera_view)

        self.tracker.predict(dt)
        was_lost = self.tracker.get_tracking_state() == TRACKING_LOST
        view_bgr = surface_to_bgr(camera_view)

        detection_local = None
        if self.detector_blind_frames > 0:
            self.detector_blind_frames -= 1
        else:
            if self.use_ai:
                detection_local = self.active_detector.detect(
                    view_bgr,
                    noise_level=self.noise.noise_level,
                    reacquiring=was_lost,
                )
            else:
                detection_local = self.active_detector.detect(
                    view_bgr,
                    adaptive=self.noise.noise_level > 0.15,
                )

        detection_scene = None
        accept = detection_local is not None
        if accept:
            detection_scene = self.camera.local_to_scene(
                detection_local[0],
                detection_local[1],
                vibration_offset_x,
                vibration_offset_y,
            )
            if was_lost and not is_plausible_reacq_detection(
                detection_scene, self.camera, self.reacquisition, self.lost_search_time
            ):
                accept = False
                detection_scene = None

        if accept and detection_scene is not None:
            if was_lost:
                self.tracker.reset(detection_scene[0], detection_scene[1])
                self.reacquisition.deactivate()
                self.reacquisition_count += 1
            else:
                self.tracker.update(detection_scene[0], detection_scene[1])
        else:
            self.tracker.mark_missed_measurement()

        estimate_x, estimate_y, _ = self.tracker.get_estimate()
        tracking_state = self.tracker.get_tracking_state()
        velocity_x, velocity_y = self.tracker.get_velocity()

        if tracking_state != TRACKING_LOST:
            self.last_locked_x = estimate_x
            self.last_locked_y = estimate_y
            self.last_velocity_x = velocity_x
            self.last_velocity_y = velocity_y

        if tracking_state == TRACKING_LOST and self.previous_tracking_state != TRACKING_LOST:
            self.reacquisition.activate(
                self.last_locked_x,
                self.last_locked_y,
                self.last_velocity_x,
                self.last_velocity_y,
                lost_time=self.lost_search_time,
            )

        pixel_error = math.hypot(estimate_x - self.beacon.x, estimate_y - self.beacon.y)
        residual_urad = self.camera.px_to_urad(pixel_error)
        readiness = self.link_readiness.compute(
            pixel_error=pixel_error,
            turbulence_strength=self.turb.strength,
            vibration_amplitude=self.vib.amplitude,
            tracking_state=tracking_state,
            snr_db=link.snr_db,
            fade_margin_db=link.fade_margin_db,
            pointing_loss=link.pointing_loss,
            scintillation=atm.scintillation,
        )

        spot_local = self.camera.scene_to_local(
            self.beacon.draw_x,
            self.beacon.draw_y,
            vibration_offset_x,
            vibration_offset_y,
        )
        spot_in_fov = (
            0.0 <= spot_local[0] < self.camera.fov_width
            and 0.0 <= spot_local[1] < self.camera.fov_height
        )
        fine_state = self.fine.update(
            dt,
            readiness_score=readiness.score,
            tracking_state=tracking_state,
            spot_local=spot_local if spot_in_fov else None,
            fov_width=self.camera.fov_width,
            fov_height=self.camera.fov_height,
            ifov_urad=self.camera.ifov_urad,
            spot_sigma_px=self.beacon.spot_sigma_px,
            camera=self.camera,
        )

        if tracking_state == TRACKING_LOST:
            self.lost_search_time += dt
            if not self.reacquisition.active:
                self.reacquisition.activate(
                    self.last_locked_x,
                    self.last_locked_y,
                    self.last_velocity_x,
                    self.last_velocity_y,
                    lost_time=self.lost_search_time,
                )
            waypoint_x, waypoint_y = self.reacquisition.get_next_waypoint(
                dt, self.camera.x, self.camera.y, lost_time=self.lost_search_time
            )
            dist_wp = math.hypot(self.camera.x - waypoint_x, self.camera.y - waypoint_y)
            slew_mult = min(MAX_ACQ_SLEW_MULTIPLIER, 3.5 + dist_wp / 100.0)
            self.camera.point_towards(
                waypoint_x, waypoint_y, dt, slew_multiplier=slew_mult
            )
        elif fine_state.active:
            # Coarse holds while fine stage is active in the real app; keep light follow.
            if self.tracker.should_drive_camera():
                self.camera.point_towards(estimate_x, estimate_y, dt, slew_multiplier=0.35)
        elif self.tracker.should_drive_camera():
            self.reacquisition.deactivate()
            self.camera.point_towards(estimate_x, estimate_y, dt)

        self.previous_tracking_state = tracking_state

        # Draw composite like main viewport
        self.screen.fill((0, 0, 0))
        overview = pygame.transform.smoothscale(self.scene_surface, self.overview_size)
        self.screen.blit(overview, (0, self.overview_y))

        fov_rect = self.camera.get_fov_rect(vibration_offset_x, vibration_offset_y)
        overlay_rect = pygame.Rect(
            int(round(fov_rect.x * self.overview_scale)),
            int(round(fov_rect.y * self.overview_scale)) + self.overview_y,
            int(round(fov_rect.width * self.overview_scale)),
            int(round(fov_rect.height * self.overview_scale)),
        )
        pygame.draw.rect(self.screen, FOV_OUTLINE_COLOR, overlay_rect, 2)
        draw_search_overlay(
            self.screen, self.reacquisition, self.overview_scale, self.overview_y
        )

        if detection_local is not None:
            draw_marker_if_in_view(
                camera_view,
                detection_local[0],
                detection_local[1],
                draw_crosshair,
                (64, 224, 255),
            )
        est_local = self.camera.scene_to_local(
            estimate_x, estimate_y, vibration_offset_x, vibration_offset_y
        )
        if est_local is not None:
            draw_marker_if_in_view(
                camera_view,
                est_local[0],
                est_local[1],
                draw_kalman_marker,
                (255, 80, 220),
            )
        draw_quad_overlay(camera_view, self.fine, fine_state.active)

        camera_display = pygame.transform.smoothscale(
            camera_view, (self.right_w, self.height)
        )
        self.screen.blit(camera_display, (self.left_w, 0))

        draw_link_readiness_gauge(
            self.screen,
            self.hud_font,
            self.width - 260,
            12,
            240,
            readiness,
        )

        hud_lines = [
            f"Detector: {self.active_detector_name}",
            f"State: {tracking_state}   Fine: {'ON' if fine_state.active else 'off'}",
            f"err: {pixel_error:.1f} px  (~{residual_urad:.0f} urad)",
            f"turb={self.turb.strength:.1f} vib={self.vib.amplitude:.1f} noise={self.noise.noise_level:.2f}",
            f"SNR {link.snr_db:.1f} dB   re-acq {self.reacquisition_count}",
        ]
        if self.detector_blind_frames > 0:
            hud_lines.append(f"DETECTOR BLIND {self.detector_blind_frames}")
        for i, line in enumerate(hud_lines):
            text = self.font.render(line, True, TITLE_FG)
            self.screen.blit(text, (12, self.height - 110 + i * 20))

        return {
            "tracking_state": tracking_state,
            "readiness": readiness.score,
            "pixel_error": pixel_error,
            "fine": fine_state.active,
        }

    def run_segment(self, segment: Segment, writer) -> None:
        frames = max(1, int(round(segment.duration_s * self.fps)))
        print(f"[{segment.label}] {frames} frames @ {self.fps} fps")

        if segment.title_only:
            for _ in range(frames):
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                render_title_card(self.screen, self.font, self.big, segment)
                pygame.display.flip()
                writer.write(surface_to_bgr_frame(self.screen))
            return

        assert segment.scenario is not None
        self._reset_world(segment.scenario, segment.detector)
        blind_armed = segment.force_blind_at_s is not None

        for i in range(frames):
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return

            self.segment_time = i * self.dt
            if (
                blind_armed
                and segment.force_blind_at_s is not None
                and self.segment_time >= segment.force_blind_at_s
            ):
                self.detector_blind_frames = DETECTOR_BLIND_FRAMES
                blind_armed = False
                print("  -> forced detector blind (demo L)")

            self._step()
            blit_caption(self.screen, self.font, self.big, segment)
            pygame.display.flip()
            writer.write(surface_to_bgr_frame(self.screen))

    def close(self) -> None:
        pygame.quit()


def open_writer(path: Path, fps: int, size: tuple[int, int]):
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    # Try MP4 then AVI fallback.
    for fourcc_name, suffix in (("mp4v", ".mp4"), ("XVID", ".avi")):
        out = path if path.suffix.lower() == suffix else path.with_suffix(suffix)
        fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
        writer = cv2.VideoWriter(str(out), fourcc, float(fps), (w, h))
        if writer.isOpened():
            return writer, out
        writer.release()
    raise RuntimeError("Could not open OpenCV VideoWriter (mp4v/XVID).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record BeamLock SIH demo video")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "logs" / "demo" / "beamlock_sih_demo.mp4",
    )
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--copy-site",
        action="store_true",
        help="Also copy the finished video into site/assets/",
    )
    args = parser.parse_args()

    import cv2  # noqa: F401 — ensure opencv available early

    recorder = DemoRecorder(fps=args.fps, base_seed=args.seed)
    writer, out_path = open_writer(
        args.out, args.fps, (recorder.width, recorder.height)
    )
    try:
        for segment in SEGMENTS:
            if segment.detector == "ai" and recorder.hybrid is None:
                # Still show segment with classical + honest caption.
                segment = Segment(
                    "UAV · Classical (AI weights unavailable)",
                    SCENARIO_UAV,
                    "classical",
                    segment.duration_s,
                    subtitle="Install/train weights for AI+fusion in the live app",
                )
            recorder.run_segment(segment, writer)
    finally:
        writer.release()
        recorder.close()

    print(f"\nSaved demo video: {out_path.resolve()}")
    print(f"Size: {out_path.stat().st_size / (1024 * 1024):.1f} MB")

    # Prefer H.264 for browser / Netlify playback.
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        h264_path = out_path.with_name(out_path.stem + "_h264.mp4")
        import subprocess

        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(out_path),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-crf",
                "23",
                "-an",
                str(h264_path),
            ],
            check=True,
            capture_output=True,
        )
        out_path.write_bytes(h264_path.read_bytes())
        print(f"Re-encoded H.264 in place: {out_path.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"H.264 re-encode skipped ({exc}). Install imageio-ffmpeg for browser-ready MP4.")

    if args.copy_site and out_path.exists():
        site_dir = ROOT / "site" / "assets"
        site_dir.mkdir(parents=True, exist_ok=True)
        dest = site_dir / out_path.name
        dest.write_bytes(out_path.read_bytes())
        print(f"Copied to {dest}")


if __name__ == "__main__":
    main()
