#!/usr/bin/env python3
"""Headless classical vs AI benchmark with matched disturbance settings.

Runs two back-to-back simulations with identical per-frame RNG seeds so
turbulence, vibration, and sensor noise realizations match frame-by-frame.
Writes named CSVs to logs/ for use in report.py compare mode.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from config import Config
from control import ReacquisitionController
from detector.classical_detector import ClassicalDetector
from disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
from metrics import LinkReadinessScore, LogSnapshot, RunLogger
from scene import Scene, Target, VirtualCamera, TRAJECTORY_CIRCULAR
from tracker import BeaconTracker, TRACKING_LOST

from main import surface_to_bgr


def seed_disturbances(frame_index: int, base_seed: int) -> None:
    np.random.seed(base_seed + frame_index)
    random.seed(base_seed + frame_index)


def run_benchmark(
    detector_name: str,
    log_path: Path,
    duration_s: float,
    fps: int,
    turbulence: float,
    vibration: float,
    sensor_noise: float,
    base_seed: int,
) -> None:
    config = Config()
    pygame.init()

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

    if detector_name == "ai":
        from detector.ai_detector import AIDetector

        active_detector = AIDetector()
        active_detector_name = "ai"
    else:
        active_detector = ClassicalDetector()
        active_detector_name = "classical"

    tracker = BeaconTracker(
        initial_x=config.screen_width / 2,
        initial_y=config.screen_height / 2,
    )
    reacquisition = ReacquisitionController(config.screen_width, config.screen_height)
    turb = TurbulenceModel(strength=turbulence)
    vib = VibrationModel(amplitude=vibration)
    noise = SensorNoiseModel(noise_level=sensor_noise)
    link_readiness = LinkReadinessScore(fov_width=camera.fov_width, fov_height=camera.fov_height)

    previous_tracking_state = TRACKING_LOST
    last_locked_x = config.screen_width / 2
    last_locked_y = config.screen_height / 2
    last_velocity_x = 0.0
    last_velocity_y = 0.0
    lost_search_time = 0.0
    reacquisition_count = 0

    logger = RunLogger(log_path)
    dt = 1.0 / fps
    total_frames = int(duration_s * fps)

    print(
        f"Running {active_detector_name} benchmark: "
        f"{duration_s:.0f}s ({total_frames} frames) -> {log_path.name}"
    )

    try:
        for frame_index in range(total_frames):
            seed_disturbances(frame_index, base_seed)

            for target in scene.targets:
                target.update(dt)

            vibration_offset_x, vibration_offset_y = vib.update(dt)
            scene.render(scene_surface)
            camera_view = camera.get_view(scene_surface, vibration_offset_x, vibration_offset_y)
            camera_view = turb.apply(camera_view)
            camera_view = noise.apply(camera_view)

            tracker.predict(dt)
            was_lost = tracker.get_tracking_state() == TRACKING_LOST
            detection_local = active_detector.detect(surface_to_bgr(camera_view))

            detection_scene = None
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
                else:
                    tracker.update(detection_scene[0], detection_scene[1])
            else:
                tracker.mark_missed_measurement()

            estimate_x, estimate_y, _ = tracker.get_estimate()
            tracking_state = tracker.get_tracking_state()
            velocity_x, velocity_y = tracker.get_velocity()

            if tracking_state != TRACKING_LOST:
                last_locked_x = estimate_x
                last_locked_y = estimate_y
                last_velocity_x = velocity_x
                last_velocity_y = velocity_y

            if tracking_state == TRACKING_LOST and previous_tracking_state != TRACKING_LOST:
                reacquisition.activate(
                    last_locked_x,
                    last_locked_y,
                    last_velocity_x,
                    last_velocity_y,
                )

            if tracking_state == TRACKING_LOST:
                lost_search_time += dt
                if detection_scene is None:
                    waypoint_x, waypoint_y = reacquisition.get_next_waypoint(
                        dt, camera.x, camera.y
                    )
                    camera.point_towards(waypoint_x, waypoint_y, dt)
            elif tracker.should_drive_camera():
                reacquisition.deactivate()
                camera.point_towards(estimate_x, estimate_y, dt)

            previous_tracking_state = tracking_state

            pixel_error = math.hypot(estimate_x - beacon.x, estimate_y - beacon.y)
            readiness = link_readiness.compute(
                pixel_error=pixel_error,
                turbulence_strength=turb.strength,
                vibration_amplitude=vib.amplitude,
                tracking_state=tracking_state,
            )

            logger.record_frame(
                tracking_state=tracking_state,
                dt=dt,
                fps=float(fps),
                pixel_error=pixel_error,
                link_readiness_score=readiness.score,
            )
            logger.maybe_log_second(
                LogSnapshot(
                    fps=float(fps),
                    tracking_state=tracking_state,
                    pixel_error=pixel_error,
                    turbulence_strength=turb.strength,
                    vibration_amplitude=vib.amplitude,
                    sensor_noise_level=noise.noise_level,
                    link_readiness_score=readiness.score,
                    cumulative_lost_seconds=lost_search_time,
                    reacquisition_count=reacquisition_count,
                    active_detector=active_detector_name,
                )
            )

            if (frame_index + 1) % fps == 0:
                elapsed_s = (frame_index + 1) // fps
                print(f"  {active_detector_name}: {elapsed_s}s / {int(duration_s)}s")
    finally:
        logger.close()
        pygame.quit()


def print_comparison_summary(classical_path: Path, ai_path: Path) -> None:
    from report import load_run_csv, summarize_run

    classical = summarize_run(load_run_csv(classical_path), classical_path.name)
    ai = summarize_run(load_run_csv(ai_path), ai_path.name)

    print("\n=== Classical vs AI (matched disturbances) ===")
    print(f"{'Metric':<28} {'Classical':>12} {'AI':>12} {'Delta':>12}")
    print("-" * 66)
    rows = [
        ("Avg pixel error (px)", classical.avg_pixel_error, ai.avg_pixel_error, False),
        ("Avg link readiness", classical.avg_link_readiness, ai.avg_link_readiness, True),
        ("% LOCKED", classical.pct_locked, ai.pct_locked, True),
        ("% LOST", classical.pct_lost, ai.pct_lost, False),
        ("Re-acquisitions", float(classical.total_reacquisitions), float(ai.total_reacquisitions), False),
    ]
    for label, a, b, higher_is_better in rows:
        delta = b - a
        if not higher_is_better and "error" in label.lower():
            delta = a - b
        elif not higher_is_better and "lost" in label.lower():
            delta = a - b
        elif label == "Re-acquisitions":
            delta = a - b
        sign = "+" if delta >= 0 else ""
        print(f"{label:<28} {a:>12.3f} {b:>12.3f} {sign}{delta:>11.3f}")
    print("=" * 66)
    if ai.avg_pixel_error < classical.avg_pixel_error:
        pct = 100.0 * (classical.avg_pixel_error - ai.avg_pixel_error) / max(classical.avg_pixel_error, 1e-6)
        print(f"AI reduced mean pixel error by {pct:.1f}% under these settings.")
    else:
        pct = 100.0 * (ai.avg_pixel_error - classical.avg_pixel_error) / max(ai.avg_pixel_error, 1e-6)
        print(f"Classical matched or beat AI by {pct:.1f}% mean pixel error — report this honestly.")
    print(f"\nOpen: streamlit run report.py")
    print(f"Compare: {classical_path.name} vs {ai_path.name}\n")


def print_matrix_summary(results: list[tuple[str, object, object]]) -> None:
    print("\n=== Scenario Matrix: Classical vs AI ===")
    print(
        f"{'Scenario':<10} {'C err':>8} {'AI err':>8} {'Δerr%':>8} "
        f"{'C lock%':>8} {'AI lock%':>8} {'C reacq':>8} {'AI reacq':>8} {'Winner':>10}"
    )
    print("-" * 90)
    for label, classical, ai in results:
        if classical.avg_pixel_error > 0:
            delta_pct = 100.0 * (classical.avg_pixel_error - ai.avg_pixel_error) / classical.avg_pixel_error
        else:
            delta_pct = 0.0
        if ai.avg_pixel_error < classical.avg_pixel_error * 0.98:
            winner = "AI"
        elif classical.avg_pixel_error < ai.avg_pixel_error * 0.98:
            winner = "Classical"
        else:
            winner = "Tie"
        # Prefer lock retention as tie-breaker for "better under stress"
        if winner == "Tie" and ai.pct_locked > classical.pct_locked + 1.0:
            winner = "AI (lock)"
        elif winner == "Tie" and classical.pct_locked > ai.pct_locked + 1.0:
            winner = "Class (lock)"
        print(
            f"{label:<10} {classical.avg_pixel_error:>8.2f} {ai.avg_pixel_error:>8.2f} "
            f"{delta_pct:>+7.1f}% {classical.pct_locked:>8.1f} {ai.pct_locked:>8.1f} "
            f"{classical.total_reacquisitions:>8} {ai.total_reacquisitions:>8} {winner:>10}"
        )
    print("=" * 90)
    print("Δerr% > 0 means AI has lower mean pixel error than classical.\n")


def run_pair(
    logs_dir: Path,
    duration: float,
    fps: int,
    turbulence: float,
    vibration: float,
    sensor_noise: float,
    seed: int,
    label: str = "",
) -> tuple[Path, Path]:
    tag = f"turb{turbulence:g}_vib{vibration:g}_noise{sensor_noise:g}"
    classical_path = logs_dir / f"classical_{tag}.csv"
    ai_path = logs_dir / f"ai_{tag}.csv"
    header = f"[{label}] " if label else ""
    print(
        f"\n{header}Settings: turbulence={turbulence}, vibration={vibration}, "
        f"sensor_noise={sensor_noise}, seed={seed}"
    )
    run_benchmark(
        "classical",
        classical_path,
        duration,
        fps,
        turbulence,
        vibration,
        sensor_noise,
        seed,
    )
    run_benchmark(
        "ai",
        ai_path,
        duration,
        fps,
        turbulence,
        vibration,
        sensor_noise,
        seed,
    )
    print_comparison_summary(classical_path, ai_path)
    return classical_path, ai_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run matched classical vs AI benchmark logs.")
    parser.add_argument("--duration", type=float, default=60.0, help="Seconds per run (default: 60)")
    parser.add_argument("--fps", type=int, default=60, help="Simulation FPS (default: 60)")
    parser.add_argument("--turbulence", type=float, default=4.0)
    parser.add_argument("--vibration", type=float, default=8.0)
    parser.add_argument("--sensor-noise", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42, help="Base RNG seed for matched disturbances")
    parser.add_argument("--logs-dir", type=Path, default=ROOT / "logs")
    parser.add_argument(
        "--matrix",
        action="store_true",
        help="Run Calm / UAV / Stress presets (matched classical vs AI each)",
    )
    args = parser.parse_args()

    logs_dir = args.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)

    if args.matrix:
        from report import load_run_csv, summarize_run
        from ui.scenarios import PRESET_ORDER, PRESETS

        matrix_results = []
        for scenario_id in PRESET_ORDER:
            preset = PRESETS[scenario_id]
            classical_path, ai_path = run_pair(
                logs_dir,
                args.duration,
                args.fps,
                preset.turbulence,
                preset.vibration,
                preset.sensor_noise,
                args.seed,
                label=preset.label,
            )
            matrix_results.append(
                (
                    preset.label,
                    summarize_run(load_run_csv(classical_path), classical_path.name),
                    summarize_run(load_run_csv(ai_path), ai_path.name),
                )
            )
        print_matrix_summary(matrix_results)
        return

    run_pair(
        logs_dir,
        args.duration,
        args.fps,
        args.turbulence,
        args.vibration,
        args.sensor_noise,
        args.seed,
    )


if __name__ == "__main__":
    main()
