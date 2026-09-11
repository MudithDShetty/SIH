"""BeamLock / FSOC Virtual Tracker — live closed-loop PAT application.

SIH26169 desktop entry point. Instantiates scene, atmospheric channel, virtual
AZ/EL camera, Classical or hybrid-AI detection, Kalman tracking, raster
re-acquisition, optional Fine 4-QD mock, and automatic performance logging.

Documentation (PDFs in ``docs/``):
  - Technical report: ``docs/sih_technical_report_v12.pdf``
  - User manual: ``docs/sih_user_manual.pdf``
  - Performance logs: ``logs/`` (see ``logs/README.md``)
  - Executable build: ``python scripts/build_exe.py``

Run::
    python main.py
    python main.py --profile ps
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import TYPE_CHECKING

import numpy as np
import pygame

if TYPE_CHECKING:
    from detector.ai_detector import AIDetector

from config import Config
from control import FinePointingController, HANDOFF_ENTER, ReacquisitionController
from control.fine_pointing import HANDOFF_CRITERIA, HANDOFF_STABLE_FRAMES
from detector.classical_detector import ClassicalDetector
from detector.hybrid_detector import HybridDetector
from disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
from disturbance.weather import NOISE_MODES, WEATHER_ORDER, WEATHER_PRESETS
from metrics import LinkReadinessResult, LinkReadinessScore, LogSnapshot, RunLogger
from metrics.session_metrics import SessionMetrics
from physics import OpticalLink
from profiles import get_profile, slew_px_s_for_profile
from scene import (
    Scene,
    Target,
    VirtualCamera,
    TRAJECTORY_CIRCULAR,
    TRAJECTORY_FIGURE8,
    TRAJECTORY_LINEAR,
    TRAJECTORY_RANDOM_WALK,
)
from tracker import BeaconTracker, TRACKING_LOST
from ui import CONTROL_PANEL_HEIGHT, ControlPanel
from ui.scenarios import PRESETS, SCENARIO_CALM, SCENARIO_STRESS, SCENARIO_UAV

FOV_OUTLINE_COLOR = (72, 220, 140)
SEARCH_PATH_COLOR = (255, 170, 60)
SEARCH_TARGET_COLOR = (255, 90, 60)
HUD_COLOR = (210, 220, 235)
DETECTOR_COLOR = (80, 220, 255)
KALMAN_COLOR = (255, 120, 220)
FINE_COLOR = (120, 255, 180)
DETECTOR_BLIND_FRAMES = 60
DETECTOR_SWITCH_GRACE_FRAMES = 15
DETECTOR_MISS_REACQ_FRAMES = 8
REACQ_VALIDATION_RADIUS_PX = 150.0
MAX_ACQ_SLEW_MULTIPLIER = 12.0


def surface_to_bgr(surface: pygame.Surface) -> np.ndarray:
    rgb = pygame.surfarray.array3d(surface)
    return np.transpose(rgb, (1, 0, 2))[:, :, ::-1].copy()


def associate_detection_local(
    detections: list[tuple[float, float, float]],
    *,
    camera: VirtualCamera,
    vibration_offset_x: float,
    vibration_offset_y: float,
    estimate_scene: tuple[float, float] | None,
    tracking_lost: bool,
) -> tuple[float, float] | None:
    """Pick one FOV detection: nearest Kalman when tracking, else brightest."""
    if not detections:
        return None
    if tracking_lost or estimate_scene is None:
        best = max(detections, key=lambda item: item[2])
        return best[0], best[1]

    best_xy: tuple[float, float] | None = None
    best_dist = float("inf")
    for local_x, local_y, _score in detections:
        scene_x, scene_y = camera.local_to_scene(
            local_x,
            local_y,
            vibration_offset_x,
            vibration_offset_y,
        )
        dist = math.hypot(scene_x - estimate_scene[0], scene_y - estimate_scene[1])
        if dist < best_dist:
            best_dist = dist
            best_xy = (local_x, local_y)
    return best_xy


def is_plausible_reacq_detection(
    detection_scene: tuple[float, float],
    camera: VirtualCamera,
    reacquisition: ReacquisitionController,
    lost_time: float = 0.0,
) -> bool:
    """Reject LOST-state false positives far from spiral / boresight."""
    det_x, det_y = detection_scene
    fov_radius = min(camera.fov_width, camera.fov_height) * 0.55
    if lost_time > 20.0:
        fov_radius *= 1.5
    dist_camera = math.hypot(det_x - camera.x, det_y - camera.y)
    if dist_camera <= fov_radius:
        return True
    if reacquisition.active:
        wp_x, wp_y = reacquisition.current_waypoint
        radius = REACQ_VALIDATION_RADIUS_PX * (1.5 if lost_time > 30.0 else 1.0)
        if math.hypot(det_x - wp_x, det_y - wp_y) <= radius:
            return True
    return False


def draw_crosshair(
    surface: pygame.Surface,
    x: float,
    y: float,
    color: tuple[int, int, int],
    size: int = 8,
) -> None:
    center_x = int(round(x))
    center_y = int(round(y))
    pygame.draw.line(
        surface,
        color,
        (center_x - size, center_y),
        (center_x + size, center_y),
        1,
    )
    pygame.draw.line(
        surface,
        color,
        (center_x, center_y - size),
        (center_x, center_y + size),
        1,
    )


def draw_kalman_marker(
    surface: pygame.Surface,
    x: float,
    y: float,
    color: tuple[int, int, int],
    radius: int = 6,
) -> None:
    center = (int(round(x)), int(round(y)))
    pygame.draw.circle(surface, color, center, radius, 1)
    pygame.draw.circle(surface, color, center, 2, 1)


def draw_marker_if_in_view(
    surface: pygame.Surface,
    local_x: float,
    local_y: float,
    draw_fn,
    color: tuple[int, int, int],
) -> None:
    width, height = surface.get_size()
    if 0 <= local_x < width and 0 <= local_y < height:
        draw_fn(surface, local_x, local_y, color)


def draw_search_overlay(
    surface: pygame.Surface,
    reacquisition: ReacquisitionController,
    scale: float,
    offset_y: int,
) -> None:
    if not reacquisition.active:
        return

    waypoints = reacquisition.get_display_waypoints()
    if len(waypoints) >= 2:
        scaled_points = [
            (
                int(round(point[0] * scale)),
                int(round(point[1] * scale)) + offset_y,
            )
            for point in waypoints
        ]
        pygame.draw.lines(surface, SEARCH_PATH_COLOR, False, scaled_points, 1)

    current = reacquisition.current_waypoint
    center = (
        int(round(reacquisition.center[0] * scale)),
        int(round(reacquisition.center[1] * scale)) + offset_y,
    )
    target = (
        int(round(current[0] * scale)),
        int(round(current[1] * scale)) + offset_y,
    )
    pygame.draw.circle(surface, SEARCH_PATH_COLOR, center, 4, 1)
    pygame.draw.circle(surface, SEARCH_TARGET_COLOR, target, 5, 1)


def draw_quad_overlay(
    surface: pygame.Surface,
    fine: FinePointingController,
    active: bool,
) -> None:
    """Draw FOV-center cross + quadrant bars for the mock 4-QD."""
    width, height = surface.get_size()
    cx, cy = width // 2, height // 2
    color = FINE_COLOR if active else (100, 110, 130)
    pygame.draw.line(surface, color, (cx - 18, cy), (cx + 18, cy), 1)
    pygame.draw.line(surface, color, (cx, cy - 18), (cx, cy + 18), 1)
    pygame.draw.circle(surface, color, (cx, cy), 22, 1)

    bar = 28
    qx = fine.quad_x
    qy = fine.quad_y
    # Right / left / down / up bars proportional to |quad|.
    if qx >= 0:
        pygame.draw.rect(
            surface,
            color,
            (cx + 26, cy - 3, int(round(bar * qx)), 6),
        )
    else:
        w = int(round(bar * -qx))
        pygame.draw.rect(surface, color, (cx - 26 - w, cy - 3, w, 6))
    if qy >= 0:
        pygame.draw.rect(
            surface,
            color,
            (cx - 3, cy + 26, 6, int(round(bar * qy))),
        )
    else:
        h = int(round(bar * -qy))
        pygame.draw.rect(surface, color, (cx - 3, cy - 26 - h, 6, h))


def readiness_color(score: float) -> tuple[int, int, int]:
    if score >= HANDOFF_ENTER:
        return (72, 220, 120)
    if score >= 0.3:
        return (240, 200, 64)
    return (235, 80, 72)


def draw_link_readiness_gauge(
    surface: pygame.Surface,
    font: pygame.font.Font,
    x: int,
    y: int,
    width: int,
    readiness: LinkReadinessResult,
) -> None:
    bar_height = 18
    label = font.render(
        f"Link Readiness: {readiness.score:.2f}",
        True,
        HUD_COLOR,
    )
    surface.blit(label, (x, y))
    bar_y = y + label.get_height() + 4
    pygame.draw.rect(surface, (40, 44, 58), (x, bar_y, width, bar_height), border_radius=3)
    fill_width = int(round(width * readiness.score))
    if fill_width > 0:
        pygame.draw.rect(
            surface,
            readiness_color(readiness.score),
            (x, bar_y, fill_width, bar_height),
            border_radius=3,
        )
    pygame.draw.rect(surface, (120, 130, 150), (x, bar_y, width, bar_height), 1, border_radius=3)

    detail_font = pygame.font.SysFont(None, 18)
    if readiness.snr_db is not None:
        detail_lines = [
            f"SNR {readiness.snr_db:.1f} dB  "
            f"fade {readiness.fade_margin_db:.1f} dB  "
            f"lock {readiness.tracking_state_subscore:.2f}  "
            f"[{readiness.mode}]",
        ]
    else:
        detail_lines = [
            f"err {readiness.pixel_error_subscore:.2f}  "
            f"turb {readiness.turbulence_subscore:.2f}  "
            f"vib {readiness.vibration_subscore:.2f}  "
            f"lock {readiness.tracking_state_subscore:.2f}",
        ]
    for index, line in enumerate(detail_lines):
        detail_surface = detail_font.render(line, True, HUD_COLOR)
        surface.blit(detail_surface, (x, bar_y + bar_height + 6 + index * 16))


def main(profile_name: str = "physics") -> None:
    profile = get_profile(profile_name)
    config = Config()
    config.screen_width = profile.screen_width
    config.screen_height = profile.screen_height
    config.fps = profile.fps

    pygame.init()
    viewport_height = config.screen_height
    window_height = viewport_height + CONTROL_PANEL_HEIGHT
    # PS 2000² may exceed some displays; allow smaller window with SCALED.
    flags = pygame.SCALED if profile.name == "ps" else 0
    screen = pygame.display.set_mode((config.screen_width, window_height), flags)
    pygame.display.set_caption(f"BeamLock / FSOC Virtual Tracker — {profile.label}")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 22)

    scene_surface = pygame.Surface((config.screen_width, config.screen_height))

    beacon = Target(
        x=config.screen_width / 2 + 150,
        y=config.screen_height / 2,
        trajectory=TRAJECTORY_CIRCULAR,
        speed=120.0 if profile.name == "physics" else 180.0,
        center_x=config.screen_width / 2,
        center_y=config.screen_height / 2,
        radius=150.0 if profile.name == "physics" else 220.0,
        screen_width=config.screen_width,
        screen_height=config.screen_height,
    )
    if profile.square_beacon:
        beacon.render_mode = "square"
        beacon.square_half_size_px = profile.beacon_half_size_px

    scene = Scene(config.screen_width, config.screen_height, targets=[beacon])
    default_slew = (
        90.0 if profile.name == "physics" else slew_px_s_for_profile(profile)
    )
    camera = VirtualCamera(
        x=config.screen_width / 2,
        y=config.screen_height / 2,
        fov_width=profile.fov_width,
        fov_height=profile.fov_height,
        max_slew_rate=default_slew,
        fov_horizontal_urad=profile.fov_horizontal_urad,
        origin_x=config.screen_width / 2,
        origin_y=config.screen_height / 2,
    )
    classical_detector = ClassicalDetector()
    ai_detector: AIDetector | None = None
    hybrid_detector: HybridDetector | None = None
    use_ai_detector = False
    active_detector: ClassicalDetector | HybridDetector = classical_detector
    tracker = BeaconTracker(
        initial_x=config.screen_width / 2,
        initial_y=config.screen_height / 2,
    )
    reacquisition = ReacquisitionController(
        config.screen_width,
        config.screen_height,
    )
    fine_pointing = FinePointingController()
    turbulence = TurbulenceModel(strength=0.0)
    vibration = VibrationModel(amplitude=0.0)
    sensor_noise = SensorNoiseModel(noise_level=0.0)
    optical_link = OpticalLink(config.link_params)
    link_readiness = LinkReadinessScore(
        fov_width=camera.fov_width,
        fov_height=camera.fov_height,
    )
    control_panel = ControlPanel(config.screen_width, viewport_height)
    # Match PS default slew on the slider when in compliance mode.
    if profile.name == "ps":
        control_panel.slew_rate_slider.set_value(default_slew)

    left_panel_width = config.screen_width // 2
    right_panel_width = config.screen_width - left_panel_width
    overview_scale = left_panel_width / config.screen_width
    overview_size = (
        left_panel_width,
        int(round(viewport_height * overview_scale)),
    )
    overview_y = (viewport_height - overview_size[1]) // 2

    trajectory_keys = {
        pygame.K_1: TRAJECTORY_LINEAR,
        pygame.K_2: TRAJECTORY_CIRCULAR,
        pygame.K_3: TRAJECTORY_RANDOM_WALK,
        pygame.K_4: TRAJECTORY_FIGURE8,
    }
    noise_mode_index = 0
    weather_index = 0
    print(f"Profile: {profile.label} ({profile.name})")
    print("Keys: 1-4 trajectories | N noise type | M weather | T detector | L blind | B beacons")
    disturbance_keys = {
        pygame.K_q: ("turbulence", +0.1),
        pygame.K_a: ("turbulence", -0.1),
        pygame.K_w: ("vibration", +0.5),
        pygame.K_s: ("vibration", -0.5),
        pygame.K_e: ("sensor", +0.05),
        pygame.K_d: ("sensor", -0.05),
    }

    tracking_confidence = 0.0
    tracking_state = TRACKING_LOST
    previous_tracking_state = TRACKING_LOST
    last_locked_x = config.screen_width / 2
    last_locked_y = config.screen_height / 2
    last_velocity_x = 0.0
    last_velocity_y = 0.0
    lost_search_time = 0.0
    reacquisition_count = 0
    detector_blind_frames = 0
    detector_grace_frames = 0
    detector_miss_streak = 0

    run_config = {
        "schema_version": "sih26169-1.1",
        "profile": profile.name,
        "profile_label": profile.label,
        "seed": 42,
        "fps": config.fps,
        "screen": [config.screen_width, config.screen_height],
        "fov_px": [camera.fov_width, camera.fov_height],
        "fov_horizontal_urad": camera.fov_horizontal_urad,
        "ifov_urad_per_px": camera.ifov_urad,
        "max_slew_urad_s": camera.max_slew_rate_urad_s,
        "max_accel_urad_s2": camera.max_accel_urad_s2,
        "handoff_criteria": HANDOFF_CRITERIA,
        "path_length_m": turbulence.channel.path_length_m
        if hasattr(turbulence, "channel")
        else None,
        "wavelength_m": config.link_params.wavelength_m,
        "sih_log_fields": [
            "simulation_duration_s",
            "fps",
            "tracking_error_px",
            "lock_retention_pct",
            "acquisition_time_s",
            "processing_time_ms",
            "reacquisition_count",
        ],
        "notes": "Software PAT testbed — not flight-qualified optics.",
    }
    run_logger = RunLogger.create_default(run_config=run_config)
    session_metrics = SessionMetrics()
    sim_elapsed = 0.0
    running = True

    def on_trajectory_change(trajectory: str) -> None:
        for target in scene.targets:
            target.set_trajectory(trajectory)
        print(f"Trajectory: {trajectory}")

    def on_targets_change(count_str: str) -> None:
        nonlocal beacon
        count = 1 if count_str != "2" else 2
        primary = scene.targets[0]
        trajectory = primary.trajectory
        if count == 1:
            scene.targets = [primary]
            beacon = primary
        else:
            if len(scene.targets) < 2:
                secondary = Target(
                    x=config.screen_width / 2 - 180,
                    y=config.screen_height / 2 + 40,
                    trajectory=trajectory,
                    speed=primary.speed * 0.85,
                    center_x=config.screen_width / 2 - 40,
                    center_y=config.screen_height / 2 + 20,
                    radius=190.0,
                    angular_speed=-primary.angular_speed * 0.9,
                    screen_width=config.screen_width,
                    screen_height=config.screen_height,
                )
                secondary.base_color = (180, 220, 255)
                scene.targets.append(secondary)
            else:
                scene.targets = scene.targets[:2]
            beacon = scene.targets[0]
            scene.targets[1].set_trajectory(trajectory)
        fine_pointing.reset()
        reacquisition.deactivate()
        print(f"Beacons: {len(scene.targets)}")

    def on_detector_change(detector_name: str) -> bool:
        nonlocal ai_detector, hybrid_detector, use_ai_detector, active_detector
        nonlocal detector_grace_frames, detector_miss_streak
        if detector_name == "ai":
            if ai_detector is None:
                try:
                    from detector.ai_detector import AIDetector

                    ai_detector = AIDetector()
                except FileNotFoundError as exc:
                    print(exc)
                    return False
            if hybrid_detector is None:
                hybrid_detector = HybridDetector(ai_detector, classical_detector)
            use_ai_detector = True
            active_detector = hybrid_detector
        else:
            use_ai_detector = False
            active_detector = classical_detector
        fine_pointing.reset()
        reacquisition.deactivate()
        detector_grace_frames = DETECTOR_SWITCH_GRACE_FRAMES
        detector_miss_streak = 0
        print(
            f"Detector: {detector_name} "
            f"(grace {DETECTOR_SWITCH_GRACE_FRAMES}f, then re-acq if blind)"
        )
        return True

    def on_preset_applied(preset) -> None:
        beacon.set_trajectory(preset.trajectory)
        control_panel.acknowledge_trajectory(preset.trajectory)
        if preset.scenario_id == SCENARIO_STRESS:
            scene.enable_clutter(star_count=55, glint_count=8, seed=7)
        elif preset.scenario_id == SCENARIO_UAV:
            scene.enable_clutter(star_count=25, glint_count=3, seed=3)
        else:
            scene.clutter = None
        print(f"Scenario: {preset.label} — {preset.description}")

    scenario_keys = {
        pygame.K_F1: SCENARIO_CALM,
        pygame.K_F2: SCENARIO_UAV,
        pygame.K_F3: SCENARIO_STRESS,
    }

    try:
        while running:
            dt_ms = clock.tick(config.fps)
            dt = dt_ms / 1000.0

            for event in pygame.event.get():
                if control_panel.handle_event(event):
                    control_panel.apply_models(
                        turbulence, vibration, sensor_noise, camera
                    )
                    control_panel.consume_selection_changes(
                        on_trajectory_change,
                        on_detector_change,
                        on_targets_change,
                    )
                    control_panel.consume_scenario_changes(on_preset_applied)
                    continue
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_t:
                        next_detector = "classical" if use_ai_detector else "ai"
                        if on_detector_change(next_detector):
                            control_panel.acknowledge_detector(next_detector)
                    elif event.key == pygame.K_b:
                        next_count = "2" if len(scene.targets) < 2 else "1"
                        on_targets_change(next_count)
                        control_panel.acknowledge_targets(next_count)
                    elif event.key == pygame.K_l:
                        detector_blind_frames = DETECTOR_BLIND_FRAMES
                        print(f"Detector blinded for {DETECTOR_BLIND_FRAMES} frames")
                    elif event.key == pygame.K_n:
                        noise_mode_index = (noise_mode_index + 1) % len(NOISE_MODES)
                        mode = NOISE_MODES[noise_mode_index]
                        sensor_noise.set_noise_type(mode)
                        print(f"Noise type: {mode}")
                    elif event.key == pygame.K_m:
                        weather_index = (weather_index + 1) % len(WEATHER_ORDER)
                        weather = WEATHER_ORDER[weather_index]
                        sensor_noise.set_weather(weather)
                        preset_w = WEATHER_PRESETS[weather]
                        # Mild turb bump for weather grades without wiping user slider.
                        if preset_w.turb_boost > 0 and turbulence.strength < preset_w.turb_boost:
                            turbulence.strength = preset_w.turb_boost
                        print(f"Weather: {preset_w.label}")
                    elif event.key in trajectory_keys:
                        on_trajectory_change(trajectory_keys[event.key])
                        control_panel.acknowledge_trajectory(trajectory_keys[event.key])
                    elif event.key in disturbance_keys:
                        kind, delta = disturbance_keys[event.key]
                        if kind == "turbulence":
                            value = turbulence.adjust_strength(delta)
                            print(f"Turbulence strength: {value:.2f}")
                        elif kind == "vibration":
                            value = vibration.adjust_amplitude(delta)
                            print(f"Vibration amplitude: {value:.2f}")
                        else:
                            value = sensor_noise.adjust_noise_level(delta)
                            print(f"Sensor noise level: {value:.2f}")
                        control_panel.sync_from_models(
                            turbulence,
                            vibration,
                            sensor_noise,
                            camera,
                            beacon.trajectory,
                            "ai" if use_ai_detector else "classical",
                        )
                    elif event.key in scenario_keys:
                        preset = control_panel.apply_preset(scenario_keys[event.key])
                        on_preset_applied(preset)
                        control_panel.apply_models(
                            turbulence, vibration, sensor_noise, camera
                        )

            control_panel.apply_models(turbulence, vibration, sensor_noise, camera)
            control_panel.consume_selection_changes(
                on_trajectory_change,
                on_detector_change,
                on_targets_change,
            )
            control_panel.consume_scenario_changes(on_preset_applied)

            for target in scene.targets:
                target.update(dt)

            vibration_offset_x, vibration_offset_y = vibration.update(dt)
            atm = turbulence.update(dt)
            wander_x_px, wander_y_px = turbulence.wander_offset_px(camera.ifov_urad)

            # Boresight residual (camera center vs geometric LOS) drives link budget.
            boresight_err_px = math.hypot(camera.x - beacon.x, camera.y - beacon.y)
            boresight_urad = camera.px_to_urad(boresight_err_px)
            link = optical_link.compute(
                residual_urad=boresight_urad,
                scintillation=atm.scintillation,
            )
            spot_sigma = optical_link.spot_sigma_px(camera.ifov_urad)
            primary_intensity = atm.scintillation * (0.35 + 0.65 * link.pointing_loss)
            for index, target in enumerate(scene.targets):
                # Secondary beacon: opposite wander phase + cooler tint (distractor).
                scale = 1.0 if index == 0 else -0.65
                intensity = primary_intensity if index == 0 else primary_intensity * 0.85
                target.set_optical_appearance(
                    draw_x=target.x + wander_x_px * scale,
                    draw_y=target.y + wander_y_px * scale,
                    spot_sigma_px=spot_sigma * (1.0 if index == 0 else 1.1),
                    intensity=intensity,
                )

            scene.render(scene_surface)

            # Platform vibration shifts FOV; atmospheric wander is on the beacon spot.
            camera_view = camera.get_view(
                scene_surface, vibration_offset_x, vibration_offset_y
            )
            camera_view = turbulence.apply(camera_view)
            camera_view = sensor_noise.apply(camera_view)

            tracker.predict(dt)
            was_lost = tracker.get_tracking_state() == TRACKING_LOST

            detection_local = None
            processing_ms = 0.0
            if detector_blind_frames > 0:
                detector_blind_frames -= 1
            else:
                detect_start = time.perf_counter()
                view_bgr = surface_to_bgr(camera_view)
                multi_beacon = len(scene.targets) > 1
                if multi_beacon and hasattr(active_detector, "detect_all"):
                    if use_ai_detector:
                        candidates = active_detector.detect_all(
                            view_bgr,
                            noise_level=sensor_noise.noise_level,
                            reacquiring=was_lost,
                        )
                    else:
                        candidates = active_detector.detect_all(
                            view_bgr,
                            adaptive=sensor_noise.noise_level > 0.15,
                        )
                    est = tracker.get_estimate()[:2] if not was_lost else None
                    detection_local = associate_detection_local(
                        candidates,
                        camera=camera,
                        vibration_offset_x=vibration_offset_x,
                        vibration_offset_y=vibration_offset_y,
                        estimate_scene=est,
                        tracking_lost=was_lost,
                    )
                elif use_ai_detector:
                    detection_local = active_detector.detect(
                        view_bgr,
                        noise_level=sensor_noise.noise_level,
                        reacquiring=was_lost,
                    )
                else:
                    detection_local = active_detector.detect(
                        view_bgr,
                        adaptive=sensor_noise.noise_level > 0.15,
                    )
                processing_ms = (time.perf_counter() - detect_start) * 1000.0

            detection_scene: tuple[float, float] | None = None
            accept_detection = detection_local is not None
            if accept_detection:
                detection_scene = camera.local_to_scene(
                    detection_local[0],
                    detection_local[1],
                    vibration_offset_x,
                    vibration_offset_y,
                )
                if was_lost and not is_plausible_reacq_detection(
                    detection_scene, camera, reacquisition, lost_search_time
                ):
                    accept_detection = False
                    detection_scene = None

            if accept_detection and detection_scene is not None:
                detector_miss_streak = 0
                detector_grace_frames = 0
                if was_lost:
                    tracker.reset(detection_scene[0], detection_scene[1])
                    reacquisition.deactivate()
                    reacquisition_count += 1
                    print(f"Re-acquired lock ({reacquisition_count})")
                else:
                    tracker.update(detection_scene[0], detection_scene[1])
                draw_marker_if_in_view(
                    camera_view,
                    detection_local[0],
                    detection_local[1],
                    draw_crosshair,
                    DETECTOR_COLOR,
                )
            else:
                if detector_grace_frames > 0:
                    detector_grace_frames -= 1
                else:
                    tracker.mark_missed_measurement()
                    detector_miss_streak += 1
                    if (
                        detector_miss_streak >= DETECTOR_MISS_REACQ_FRAMES
                        and tracker.get_tracking_state() != TRACKING_LOST
                    ):
                        tracker.force_lost()

            estimate_x, estimate_y, tracking_confidence = tracker.get_estimate()
            tracking_state = tracker.get_tracking_state()
            velocity_x, velocity_y = tracker.get_velocity()

            if tracking_state != TRACKING_LOST:
                last_locked_x = estimate_x
                last_locked_y = estimate_y
                last_velocity_x = velocity_x
                last_velocity_y = velocity_y

            if (
                tracking_state == TRACKING_LOST
                and previous_tracking_state != TRACKING_LOST
            ):
                reacquisition.activate(
                    last_locked_x,
                    last_locked_y,
                    last_velocity_x,
                    last_velocity_y,
                    lost_time=lost_search_time,
                    force_raster=lost_search_time >= 8.0,
                    uncertainty_radius_px=3.0 * tracker.position_sigma_px(),
                )
                fine_pointing.reset()
                print("Entering LOST state, starting spiral search")

            pixel_error = math.hypot(estimate_x - beacon.x, estimate_y - beacon.y)
            angular_error_urad = camera.pixel_error_to_urad(pixel_error)
            readiness = link_readiness.compute(
                pixel_error=pixel_error,
                turbulence_strength=turbulence.strength,
                vibration_amplitude=vibration.amplitude,
                tracking_state=tracking_state,
                snr_db=link.snr_db,
                fade_margin_db=link.fade_margin_db,
                pointing_loss=link.pointing_loss,
                scintillation=atm.scintillation,
            )

            # Apparent beacon in FOV = physical 4-QD irradiance centroid.
            spot_local = camera.scene_to_local(
                beacon.draw_x,
                beacon.draw_y,
                vibration_offset_x,
                vibration_offset_y,
            )
            spot_in_fov = (
                0.0 <= spot_local[0] < camera.fov_width
                and 0.0 <= spot_local[1] < camera.fov_height
            )

            fine_state = fine_pointing.update(
                dt,
                readiness_score=readiness.score,
                tracking_state=tracking_state,
                spot_local=spot_local if spot_in_fov else None,
                fov_width=camera.fov_width,
                fov_height=camera.fov_height,
                ifov_urad=camera.ifov_urad,
                spot_sigma_px=beacon.spot_sigma_px,
                camera=camera,
            )

            if tracking_state == TRACKING_LOST:
                lost_search_time += dt
                if not reacquisition.active:
                    reacquisition.activate(
                        last_locked_x,
                        last_locked_y,
                        last_velocity_x,
                        last_velocity_y,
                        lost_time=lost_search_time,
                        force_raster=lost_search_time >= 8.0,
                        uncertainty_radius_px=3.0 * tracker.position_sigma_px(),
                    )
                pred_x, pred_y = reacquisition.predict_target(
                    last_locked_x,
                    last_locked_y,
                    last_velocity_x,
                    last_velocity_y,
                    lost_search_time,
                )
                waypoint_x, waypoint_y = reacquisition.get_next_waypoint(
                    dt,
                    camera.x,
                    camera.y,
                    lost_time=lost_search_time,
                )
                aim_x, aim_y = waypoint_x, waypoint_y
                dist_wp = math.hypot(camera.x - aim_x, camera.y - aim_y)
                slew_mult = min(
                    MAX_ACQ_SLEW_MULTIPLIER,
                    3.5 + dist_wp / 100.0,
                )
                camera.point_towards(aim_x, aim_y, dt, slew_multiplier=slew_mult)
            elif fine_state.active:
                reacquisition.deactivate()
                # Fine FSM already slewed the camera inside update().
            elif tracker.should_drive_camera():
                reacquisition.deactivate()
                camera.point_towards(estimate_x, estimate_y, dt)

            previous_tracking_state = tracking_state

            estimate_local = camera.scene_to_local(
                estimate_x,
                estimate_y,
                vibration_offset_x,
                vibration_offset_y,
            )
            draw_marker_if_in_view(
                camera_view,
                estimate_local[0],
                estimate_local[1],
                draw_kalman_marker,
                KALMAN_COLOR,
            )
            draw_quad_overlay(camera_view, fine_pointing, fine_state.active)

            screen.fill((0, 0, 0))

            overview = pygame.transform.smoothscale(scene_surface, overview_size)
            screen.blit(overview, (0, overview_y))
            draw_search_overlay(screen, reacquisition, overview_scale, overview_y)

            fov_rect = camera.get_fov_rect(vibration_offset_x, vibration_offset_y)
            overlay_rect = pygame.Rect(
                int(round(fov_rect.x * overview_scale)),
                int(round(fov_rect.y * overview_scale)) + overview_y,
                int(round(fov_rect.width * overview_scale)),
                int(round(fov_rect.height * overview_scale)),
            )
            pygame.draw.rect(screen, FOV_OUTLINE_COLOR, overlay_rect, 2)

            camera_display = pygame.transform.smoothscale(
                camera_view, (right_panel_width, viewport_height)
            )
            screen.blit(camera_display, (left_panel_width, 0))

            target_visible = camera.is_visible(
                beacon.x, beacon.y, vibration_offset_x, vibration_offset_y
            )
            fps = clock.get_fps()
            active_detector_name = "ai" if use_ai_detector else "classical"
            sim_elapsed += dt
            session_metrics.record_frame(
                dt=dt,
                tracking_state=tracking_state,
                pixel_error=pixel_error,
                processing_time_ms=processing_ms,
                elapsed_s=sim_elapsed,
                angular_error_urad=angular_error_urad,
                pat_stage=fine_state.stage,
                handoff_count=fine_state.handoff_count,
            )
            r0_cm = atm.r0_m * 100.0
            stage_label = (
                f"FINE 4QD  resid {fine_state.residual_urad:.0f} urad  "
                f"q=({fine_state.quad_x:+.2f},{fine_state.quad_y:+.2f})  "
                f"handoffs {fine_state.handoff_count}"
                if fine_state.active
                else (
                    f"COARSE  (fine if readiness>={HANDOFF_ENTER:.2f} "
                    f"x{HANDOFF_STABLE_FRAMES}f  stable={fine_state.stable_frames})"
                )
            )
            search_label = (
                reacquisition.mode.upper()
                if reacquisition.active
                else "—"
            )
            hud_lines = [
                (
                    f"AZ/EL: {camera.az_urad:.0f}/{camera.el_urad:.0f} urad  "
                    f"IFOV: {camera.ifov_urad:.2f} urad/px"
                ),
                (
                    f"Detector: {'AI+fusion' if use_ai_detector else 'classical'}  "
                    f"Beacons: {len(scene.targets)}  PAT: {stage_label}"
                ),
                f"Target visible: {target_visible}",
                f"FPS: {fps:.0f}  Detect: {processing_ms:.1f} ms",
                (
                    f"Slew: {camera.max_slew_rate:.0f} px/s "
                    f"({camera.max_slew_rate_urad_s:.0f} urad/s)"
                    + (
                        f"  x{min(MAX_ACQ_SLEW_MULTIPLIER, 3.5 + math.hypot(camera.x - reacquisition.current_waypoint[0], camera.y - reacquisition.current_waypoint[1]) / 100.0):.0f} ACQ"
                        if tracking_state == TRACKING_LOST
                        else ""
                    )
                ),
                (
                    f"Error: {angular_error_urad:.0f} urad ({pixel_error:.2f} px)  "
                    f"Boresight: {boresight_urad:.0f} urad"
                ),
                (
                    f"Cn2: {atm.cn2:.2e}  r0: {r0_cm:.1f} cm  "
                    f"I: {atm.scintillation:.2f}  SNR: {link.snr_db:.1f} dB"
                ),
                (
                    f"Tracking: {tracking_state}  Search: {search_label}  "
                    f"Conf: {tracking_confidence:.3f}"
                ),
                f"Lost/search: {lost_search_time:.1f}s  Re-acqs: {reacquisition_count}",
            ]
            for index, line in enumerate(hud_lines):
                text_surface = font.render(line, True, HUD_COLOR)
                screen.blit(text_surface, (8, 8 + index * 20))

            draw_link_readiness_gauge(
                screen,
                font,
                x=config.screen_width - 300,
                y=12,
                width=280,
                readiness=readiness,
            )
            if fine_state.active:
                badge = font.render(
                    f"FINE ACTIVE  {fine_state.time_in_fine_s:.1f}s",
                    True,
                    FINE_COLOR,
                )
                screen.blit(badge, (config.screen_width - 300, 78))

            control_panel.draw(screen)

            run_logger.record_frame(
                tracking_state=tracking_state,
                dt=dt,
                fps=fps,
                pixel_error=pixel_error,
                link_readiness_score=readiness.score,
                angular_error_urad=angular_error_urad,
            )
            run_logger.maybe_log_second(
                LogSnapshot(
                    fps=fps,
                    tracking_state=tracking_state,
                    pixel_error=pixel_error,
                    turbulence_strength=turbulence.strength,
                    vibration_amplitude=vibration.amplitude,
                    sensor_noise_level=sensor_noise.noise_level,
                    link_readiness_score=readiness.score,
                    cumulative_lost_seconds=lost_search_time,
                    reacquisition_count=reacquisition_count,
                    active_detector=active_detector_name,
                    angular_error_urad=angular_error_urad,
                    boresight_urad=boresight_urad,
                    az_urad=camera.az_urad,
                    el_urad=camera.el_urad,
                    pat_stage=fine_state.stage,
                    handoff_count=fine_state.handoff_count,
                )
            )

            pygame.display.flip()
    finally:
        summary_path = run_logger.log_path.with_suffix(".summary.json")
        session_metrics.write_summary(
            summary_path,
            fps_avg=clock.get_fps(),
            active_detector="ai" if use_ai_detector else "classical",
            reacquisition_count=reacquisition_count,
            profile=profile.name,
            log_csv=run_logger.log_path.name,
        )
        print(f"Session summary: {summary_path}")
        run_logger.close()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BeamLock / FSOC Virtual Tracker")
    parser.add_argument(
        "--profile",
        default="physics",
        choices=("physics", "ps"),
        help="physics = current BeamLock sandbox; ps = SIH26169 Parameters table mode",
    )
    args = parser.parse_args()
    main(profile_name=args.profile)
