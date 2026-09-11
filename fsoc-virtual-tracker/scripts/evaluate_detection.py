#!/usr/bin/env python3
"""Clutter stress: Pd / Pfa for classical (and optional AI) detectors.

Generates FOV frames with a known beacon + star/glint clutter, scores detections
within a gate of the true local position.
"""

from __future__ import annotations

import argparse
import json
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
from detector.classical_detector import ClassicalDetector
from disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
from scene import Scene, Target, VirtualCamera, TRAJECTORY_CIRCULAR
from ui.scenarios import PRESETS, SCENARIO_STRESS, SCENARIO_UAV

from main import surface_to_bgr

GATE_PX = 18.0


def evaluate_detector(
    detector,
    *,
    frames: int,
    scenario_id: str,
    seed: int,
    use_ai: bool,
) -> dict:
    random.seed(seed)
    np.random.seed(seed)
    config = Config()
    preset = PRESETS[scenario_id]
    dt = 1.0 / 60.0

    beacon = Target(
        x=config.screen_width / 2 + 80,
        y=config.screen_height / 2,
        trajectory=TRAJECTORY_CIRCULAR,
        speed=100.0,
        center_x=config.screen_width / 2,
        center_y=config.screen_height / 2,
        radius=120.0,
        screen_width=config.screen_width,
        screen_height=config.screen_height,
    )
    scene = Scene(config.screen_width, config.screen_height, targets=[beacon])
    scene.enable_clutter(star_count=60, glint_count=10, seed=seed)
    camera = VirtualCamera(
        x=config.screen_width / 2,
        y=config.screen_height / 2,
        fov_width=400,
        fov_height=300,
        max_slew_rate=preset.slew_rate,
        origin_x=config.screen_width / 2,
        origin_y=config.screen_height / 2,
    )
    turbulence = TurbulenceModel(strength=preset.turbulence)
    vibration = VibrationModel(amplitude=preset.vibration)
    sensor_noise = SensorNoiseModel(noise_level=preset.sensor_noise)
    scene_surface = pygame.Surface((config.screen_width, config.screen_height))

    tp = fp = fn = tn = 0
    # Also run empty-FOV false alarm trials by hiding the beacon intensity.
    for i in range(frames):
        beacon.update(dt)
        vib_x, vib_y = vibration.update(dt)
        atm = turbulence.update(dt)
        wander_x, wander_y = turbulence.wander_offset_px(camera.ifov_urad)
        hide = i % 5 == 0  # every 5th frame: no beacon (Pfa probe)
        beacon.set_optical_appearance(
            draw_x=beacon.x + wander_x,
            draw_y=beacon.y + wander_y,
            spot_sigma_px=max(2.5, 2.5 + 0.35 * turbulence.strength),
            intensity=0.0 if hide else atm.scintillation,
        )
        # Keep camera near beacon for visibility when present.
        camera.x = beacon.x + random.uniform(-40, 40)
        camera.y = beacon.y + random.uniform(-30, 30)
        scene.render(scene_surface)
        view = camera.get_view(scene_surface, vib_x, vib_y)
        view = turbulence.apply(view)
        view = sensor_noise.apply(view)
        bgr = surface_to_bgr(view)

        if use_ai:
            det = detector.detect(bgr)
        else:
            det = detector.detect(bgr, adaptive=True)

        true_local = camera.scene_to_local(
            beacon.draw_x, beacon.draw_y, vib_x, vib_y
        )
        in_fov = (
            0 <= true_local[0] < camera.fov_width
            and 0 <= true_local[1] < camera.fov_height
            and not hide
        )

        if det is None:
            if in_fov:
                fn += 1
            else:
                tn += 1
            continue

        if in_fov:
            err = (
                (det[0] - true_local[0]) ** 2 + (det[1] - true_local[1]) ** 2
            ) ** 0.5
            if err <= GATE_PX:
                tp += 1
            else:
                fp += 1  # wrong blob while beacon present
        else:
            fp += 1

    pd = tp / max(tp + fn, 1)
    pfa = fp / max(fp + tn, 1)
    return {
        "detector": "ai" if use_ai else "classical",
        "scenario": scenario_id,
        "frames": frames,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "Pd": round(pd, 4),
        "Pfa": round(pfa, 4),
        "gate_px": GATE_PX,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Detector Pd/Pfa under clutter")
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument(
        "--scenario",
        choices=[SCENARIO_UAV, SCENARIO_STRESS],
        default=SCENARIO_STRESS,
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ai", action="store_true", help="Also evaluate AI detector")
    args = parser.parse_args()

    pygame.init()
    results = [
        evaluate_detector(
            ClassicalDetector(),
            frames=args.frames,
            scenario_id=args.scenario,
            seed=args.seed,
            use_ai=False,
        )
    ]
    if args.ai:
        try:
            from detector.ai_detector import AIDetector

            results.append(
                evaluate_detector(
                    AIDetector(),
                    frames=args.frames,
                    scenario_id=args.scenario,
                    seed=args.seed + 1,
                    use_ai=True,
                )
            )
        except FileNotFoundError as exc:
            print(f"AI skipped: {exc}")

    out_dir = ROOT / "logs" / "detection"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"pd_pfa_{args.scenario}.json"
    out_path.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

    print("\n=== Detection ROC-lite (clutter) ===")
    for row in results:
        print(
            f"{row['detector']:10s}  Pd={row['Pd']:.3f}  Pfa={row['Pfa']:.3f}  "
            f"tp={row['tp']} fp={row['fp']} fn={row['fn']} tn={row['tn']}"
        )
    print(f"Wrote {out_path}")
    pygame.quit()


if __name__ == "__main__":
    main()
