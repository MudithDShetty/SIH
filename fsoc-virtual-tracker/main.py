import math
import sys
import time

import numpy as np
import pygame

from config import Config
from control import ReacquisitionController
from detector.classical_detector import ClassicalDetector
from disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
from metrics import LinkReadinessResult, LinkReadinessScore, LogSnapshot, RunLogger
from metrics.session_metrics import SessionMetrics
from scene import (
    Scene,
    Target,
    VirtualCamera,
    TRAJECTORY_CIRCULAR,
    TRAJECTORY_LINEAR,
    TRAJECTORY_RANDOM_WALK,
)
from tracker import BeaconTracker, TRACKING_LOST
from ui import CONTROL_PANEL_HEIGHT, ControlPanel
from ui.scenarios import PRESET_ORDER, PRESETS, SCENARIO_CALM, SCENARIO_STRESS, SCENARIO_UAV

FOV_OUTLINE_COLOR = (72, 220, 140)
SEARCH_PATH_COLOR = (255, 170, 60)
SEARCH_TARGET_COLOR = (255, 90, 60)
HUD_COLOR = (210, 220, 235)
DETECTOR_COLOR = (80, 220, 255)
KALMAN_COLOR = (255, 120, 220)
DETECTOR_BLIND_FRAMES = 60


def surface_to_bgr(surface: pygame.Surface) -> np.ndarray:
    rgb = pygame.surfarray.array3d(surface)
    return np.transpose(rgb, (1, 0, 2))[:, :, ::-1].copy()


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


def readiness_color(score: float) -> tuple[int, int, int]:
    if score >= 0.7:
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
    detail_lines = [
        f"err {readiness.pixel_error_subscore:.2f}  "
        f"turb {readiness.turbulence_subscore:.2f}  "
        f"vib {readiness.vibration_subscore:.2f}  "
        f"lock {readiness.tracking_state_subscore:.2f}",
    ]
    for index, line in enumerate(detail_lines):
        detail_surface = detail_font.render(line, True, HUD_COLOR)
        surface.blit(detail_surface, (x, bar_y + bar_height + 6 + index * 16))


def main() -> None:
    config = Config()

    pygame.init()
    viewport_height = config.screen_height
    window_height = viewport_height + CONTROL_PANEL_HEIGHT
    screen = pygame.display.set_mode((config.screen_width, window_height))
    pygame.display.set_caption("FSOC Virtual Tracker")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 22)

    scene_surface = pygame.Surface((config.screen_width, config.screen_height))

    beacon = Target(
        x=config.screen_width / 2 + 150,
        y=config.screen_height / 2,
        trajectory=TRAJECTORY_CIRCULAR,
        speed=120.0,
        center_x=config.screen_width / 2,
        center_y=config.screen_height / 2,
        radius=150.0,
        screen_width=config.screen_width,
        screen_height=config.screen_height,
    )
    scene = Scene(config.screen_width, config.screen_height, targets=[beacon])
    camera = VirtualCamera(
        x=config.screen_width / 2,
        y=config.screen_height / 2,
        fov_width=400,
        fov_height=300,
        max_slew_rate=90.0,
    )
    classical_detector = ClassicalDetector()
    ai_detector: AIDetector | None = None
    use_ai_detector = False
    active_detector: ClassicalDetector | AIDetector = classical_detector
    tracker = BeaconTracker(
        initial_x=config.screen_width / 2,
        initial_y=config.screen_height / 2,
    )
    reacquisition = ReacquisitionController(
        config.screen_width,
        config.screen_height,
    )
    turbulence = TurbulenceModel(strength=0.0)
    vibration = VibrationModel(amplitude=0.0)
    sensor_noise = SensorNoiseModel(noise_level=0.0)
    link_readiness = LinkReadinessScore(
        fov_width=camera.fov_width,
        fov_height=camera.fov_height,
    )
    control_panel = ControlPanel(config.screen_width, viewport_height)

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
    }
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

    run_logger = RunLogger.create_default()
    session_metrics = SessionMetrics()
    sim_elapsed = 0.0
    running = True

    def on_trajectory_change(trajectory: str) -> None:
        beacon.set_trajectory(trajectory)
        print(f"Trajectory: {trajectory}")

    def on_detector_change(detector_name: str) -> bool:
        nonlocal ai_detector, use_ai_detector, active_detector
        if detector_name == "ai":
            if ai_detector is None:
                try:
                    from detector.ai_detector import AIDetector

                    ai_detector = AIDetector()
                except FileNotFoundError as exc:
                    print(exc)
                    return False
            use_ai_detector = True
            active_detector = ai_detector
        else:
            use_ai_detector = False
            active_detector = classical_detector
        print(f"Detector: {detector_name}")
        return True

    def on_preset_applied(preset) -> None:
        beacon.set_trajectory(preset.trajectory)
        control_panel.acknowledge_trajectory(preset.trajectory)
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
                    elif event.key == pygame.K_l:
                        detector_blind_frames = DETECTOR_BLIND_FRAMES
                        print(f"Detector blinded for {DETECTOR_BLIND_FRAMES} frames")
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
            )
            control_panel.consume_scenario_changes(on_preset_applied)

            for target in scene.targets:
                target.update(dt)

            vibration_offset_x, vibration_offset_y = vibration.update(dt)

            scene.render(scene_surface)

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
                detection_local = active_detector.detect(surface_to_bgr(camera_view))
                processing_ms = (time.perf_counter() - detect_start) * 1000.0

            detection_scene: tuple[float, float] | None = None
            if detection_local is not None:
                detection_scene = camera.local_to_scene(
                    detection_local[0],
                    detection_local[1],
                    vibration_offset_x,
                    vibration_offset_y,
                )
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
                tracker.mark_missed_measurement()

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
                )
                print("Entering LOST state, starting spiral search")

            if tracking_state == TRACKING_LOST:
                lost_search_time += dt
                if detection_scene is None:
                    waypoint_x, waypoint_y = reacquisition.get_next_waypoint(
                        dt,
                        camera.x,
                        camera.y,
                    )
                    camera.point_towards(waypoint_x, waypoint_y, dt)
            elif tracker.should_drive_camera():
                reacquisition.deactivate()
                camera.point_towards(estimate_x, estimate_y, dt)

            previous_tracking_state = tracking_state

            pixel_error = math.hypot(estimate_x - beacon.x, estimate_y - beacon.y)
            angular_error_urad = camera.pixel_error_to_urad(pixel_error)
            readiness = link_readiness.compute(
                pixel_error=pixel_error,
                turbulence_strength=turbulence.strength,
                vibration_amplitude=vibration.amplitude,
                tracking_state=tracking_state,
            )

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
            )
            hud_lines = [
                f"Camera: ({camera.x:.1f}, {camera.y:.1f})",
                f"Detector: {active_detector_name}",
                f"Target visible: {target_visible}",
                f"FPS: {fps:.0f}  Detect: {processing_ms:.1f} ms",
                f"Slew rate: {camera.max_slew_rate:.0f} px/s",
                f"Error: {pixel_error:.2f} px ({angular_error_urad:.0f} urad)",
                f"Tracking: {tracking_state}  Confidence: {tracking_confidence:.3f}",
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

            control_panel.draw(screen)

            run_logger.record_frame(
                tracking_state=tracking_state,
                dt=dt,
                fps=fps,
                pixel_error=pixel_error,
                link_readiness_score=readiness.score,
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
        )
        print(f"Session summary: {summary_path}")
        run_logger.close()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
