#!/usr/bin/env python3
"""Monte Carlo acquisition-time trials vs ESA ESTOL-class <60 s bound.

Forces LOST, runs re-acquisition under a named scenario, records time-to-lock.
Writes JSON + CSV under logs/monte_carlo/.
"""

from __future__ import annotations

import argparse
import json
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
from scene import Scene, Target, VirtualCamera, TRAJECTORY_CIRCULAR
from tracker import BeaconTracker, TRACKING_LOST
from ui.scenarios import PRESETS, SCENARIO_CALM, SCENARIO_STRESS, SCENARIO_UAV

from main import surface_to_bgr

ESTOL_WARM_START_S = 60.0


def run_one_trial(
    *,
    seed: int,
    scenario_id: str,
    max_seconds: float,
    fps: int,
) -> dict:
    random.seed(seed)
    np.random.seed(seed)

    config = Config()
    preset = PRESETS[scenario_id]
    dt = 1.0 / fps

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
    beacon.set_trajectory(preset.trajectory)
    scene = Scene(config.screen_width, config.screen_height, targets=[beacon])
    if scenario_id != SCENARIO_CALM:
        scene.enable_clutter(
            star_count=40 if scenario_id == SCENARIO_STRESS else 20,
            glint_count=6 if scenario_id == SCENARIO_STRESS else 2,
            seed=seed,
        )

    camera = VirtualCamera(
        x=config.screen_width / 2,
        y=config.screen_height / 2,
        fov_width=400,
        fov_height=300,
        max_slew_rate=preset.slew_rate,
        origin_x=config.screen_width / 2,
        origin_y=config.screen_height / 2,
    )
    detector = ClassicalDetector()
    tracker = BeaconTracker(
        initial_x=config.screen_width / 2,
        initial_y=config.screen_height / 2,
    )
    reacq = ReacquisitionController(config.screen_width, config.screen_height)
    turbulence = TurbulenceModel(strength=preset.turbulence)
    vibration = VibrationModel(amplitude=preset.vibration)
    sensor_noise = SensorNoiseModel(noise_level=preset.sensor_noise)
    scene_surface = pygame.Surface((config.screen_width, config.screen_height))

    # Warm lock then force LOST.
    for _ in range(int(fps * 1.5)):
        beacon.update(dt)
        vib_x, vib_y = vibration.update(dt)
        turbulence.update(dt)
        scene.render(scene_surface)
        view = camera.get_view(scene_surface, vib_x, vib_y)
        view = turbulence.apply(view)
        view = sensor_noise.apply(view)
        tracker.predict(dt)
        det = detector.detect(surface_to_bgr(view), adaptive=True)
        if det is not None:
            sx, sy = camera.local_to_scene(det[0], det[1], vib_x, vib_y)
            if tracker.get_tracking_state() == TRACKING_LOST:
                tracker.reset(sx, sy)
            else:
                tracker.update(sx, sy)
            if tracker.should_drive_camera():
                ex, ey, _ = tracker.get_estimate()
                camera.point_towards(ex, ey, dt)

    tracker.force_lost()
    # Displace camera so the beacon leaves FOV — forces real search, not instant re-lock.
    camera.x = max(80.0, beacon.x - camera.fov_width * 1.2)
    camera.y = max(80.0, beacon.y - camera.fov_height * 1.1)
    camera._az_rate_urad_s = 0.0
    camera._el_rate_urad_s = 0.0
    ex, ey, _ = tracker.get_estimate()
    vx, vy = tracker.get_velocity()
    reacq.activate(
        ex,
        ey,
        vx,
        vy,
        uncertainty_radius_px=max(80.0, 3.0 * tracker.position_sigma_px()),
    )

    elapsed = 0.0
    acquired = False
    while elapsed < max_seconds:
        beacon.update(dt)
        vib_x, vib_y = vibration.update(dt)
        turbulence.update(dt)
        scene.render(scene_surface)
        view = camera.get_view(scene_surface, vib_x, vib_y)
        view = turbulence.apply(view)
        view = sensor_noise.apply(view)
        tracker.predict(dt)
        det = detector.detect(surface_to_bgr(view), adaptive=True)
        if det is not None:
            sx, sy = camera.local_to_scene(det[0], det[1], vib_x, vib_y)
            if tracker.get_tracking_state() == TRACKING_LOST:
                tracker.reset(sx, sy)
                reacq.deactivate()
                acquired = True
                elapsed += dt
                break
            tracker.update(sx, sy)
        else:
            tracker.mark_missed_measurement()

        if tracker.get_tracking_state() == TRACKING_LOST:
            wx, wy = reacq.get_next_waypoint(dt, camera.x, camera.y, lost_time=elapsed)
            dist = math.hypot(camera.x - wx, camera.y - wy)
            camera.point_towards(wx, wy, dt, slew_multiplier=min(12.0, 3.5 + dist / 100.0))
        elif tracker.should_drive_camera():
            ex, ey, _ = tracker.get_estimate()
            camera.point_towards(ex, ey, dt)

        elapsed += dt

    return {
        "seed": seed,
        "scenario": scenario_id,
        "acquired": acquired,
        "time_to_lock_s": round(elapsed, 3) if acquired else None,
        "timed_out": not acquired,
        "estol_pass": bool(acquired and elapsed < ESTOL_WARM_START_S),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Monte Carlo acquisition timing")
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument(
        "--scenario",
        choices=[SCENARIO_CALM, SCENARIO_UAV, SCENARIO_STRESS],
        default=SCENARIO_UAV,
    )
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    pygame.init()
    results = []
    for i in range(args.trials):
        trial_seed = args.seed + i * 17
        result = run_one_trial(
            seed=trial_seed,
            scenario_id=args.scenario,
            max_seconds=args.max_seconds,
            fps=60,
        )
        results.append(result)
        status = (
            f"{result['time_to_lock_s']:.2f}s"
            if result["acquired"]
            else "TIMEOUT"
        )
        print(f"[{i + 1}/{args.trials}] seed={trial_seed}  {status}")

    times = [r["time_to_lock_s"] for r in results if r["acquired"]]
    times_sorted = sorted(times)
    summary = {
        "scenario": args.scenario,
        "trials": args.trials,
        "acquired": len(times),
        "timeouts": args.trials - len(times),
        "estol_bound_s": ESTOL_WARM_START_S,
        "estol_pass_count": sum(1 for r in results if r["estol_pass"]),
        "median_s": times_sorted[len(times_sorted) // 2] if times_sorted else None,
        "p95_s": times_sorted[int(0.95 * (len(times_sorted) - 1))] if times_sorted else None,
        "mean_s": sum(times) / len(times) if times else None,
        "results": results,
    }

    out_dir = ROOT / "logs" / "monte_carlo"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"acquisition_{args.scenario}_{args.trials}trials.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n=== Acquisition Monte Carlo ===")
    print(f"Scenario: {args.scenario}")
    print(f"Acquired: {summary['acquired']}/{args.trials}")
    print(f"ESTOL <{ESTOL_WARM_START_S:.0f}s passes: {summary['estol_pass_count']}/{args.trials}")
    if times:
        print(f"Median: {summary['median_s']:.2f}s  p95: {summary['p95_s']:.2f}s  mean: {summary['mean_s']:.2f}s")
    print(f"Wrote {out_path}")
    pygame.quit()


if __name__ == "__main__":
    main()
