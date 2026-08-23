#!/usr/bin/env python3
"""Generate synthetic YOLO training data from the FSOC simulation pipeline."""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from config import Config
from disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
from disturbance.disturbance import _surface_to_bgr
from scene import Scene, Target, VirtualCamera
from scene.scene import (
    TRAJECTORY_CIRCULAR,
    TRAJECTORY_LINEAR,
    TRAJECTORY_RANDOM_WALK,
)

BEACON_CLASS_ID = 0
BEACON_BOX_SIZE = 16
DEFAULT_NUM_FRAMES = 2400
VAL_SPLIT = 0.2


def surface_to_bgr(surface: pygame.Surface) -> np.ndarray:
    return _surface_to_bgr(surface)


def write_yolo_label(
    label_path: Path,
    local_x: float,
    local_y: float,
    image_width: int,
    image_height: int,
    box_size: int = BEACON_BOX_SIZE,
) -> None:
    x_center = local_x / image_width
    y_center = local_y / image_height
    width = box_size / image_width
    height = box_size / image_height
    label_path.write_text(
        f"{BEACON_CLASS_ID} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n",
        encoding="utf-8",
    )


def write_data_yaml(data_dir: Path) -> None:
    yaml_path = data_dir / "data.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                f"path: {data_dir.resolve().as_posix()}",
                "train: images/train",
                "val: images/val",
                "names:",
                "  0: beacon",
                "",
            ]
        ),
        encoding="utf-8",
    )


def ensure_split_dirs(data_dir: Path) -> dict[str, Path]:
    paths = {}
    for split in ("train", "val"):
        paths[f"images_{split}"] = data_dir / "images" / split
        paths[f"labels_{split}"] = data_dir / "labels" / split
        paths[f"images_{split}"].mkdir(parents=True, exist_ok=True)
        paths[f"labels_{split}"].mkdir(parents=True, exist_ok=True)
    return paths


def random_scenario(config: Config) -> tuple[Target, VirtualCamera, TurbulenceModel, VibrationModel, SensorNoiseModel]:
    trajectory = random.choice(
        [TRAJECTORY_LINEAR, TRAJECTORY_CIRCULAR, TRAJECTORY_RANDOM_WALK]
    )
    target = Target(
        x=random.uniform(200, config.screen_width - 200),
        y=random.uniform(150, config.screen_height - 150),
        trajectory=trajectory,
        speed=random.uniform(60.0, 160.0),
        center_x=config.screen_width / 2 + random.uniform(-120, 120),
        center_y=config.screen_height / 2 + random.uniform(-80, 80),
        radius=random.uniform(80.0, 220.0),
        screen_width=config.screen_width,
        screen_height=config.screen_height,
    )
    camera = VirtualCamera(
        x=target.x + random.uniform(-120.0, 120.0),
        y=target.y + random.uniform(-90.0, 90.0),
        fov_width=400,
        fov_height=300,
        max_slew_rate=120.0,
    )
    turbulence = TurbulenceModel(strength=random.uniform(0.0, 5.0))
    vibration = VibrationModel(amplitude=random.uniform(0.0, 18.0))
    sensor_noise = SensorNoiseModel(noise_level=random.uniform(0.0, 0.65))
    return target, camera, turbulence, vibration, sensor_noise


def generate_dataset(num_frames: int, data_dir: Path, seed: int = 42) -> int:
    random.seed(seed)
    np.random.seed(seed)

    pygame.init()
    config = Config()
    scene_surface = pygame.Surface((config.screen_width, config.screen_height))
    paths = ensure_split_dirs(data_dir)
    write_data_yaml(data_dir)

    saved = 0
    attempts = 0
    max_attempts = num_frames * 20

    while saved < num_frames and attempts < max_attempts:
        attempts += 1
        target, camera, turbulence, vibration, sensor_noise = random_scenario(config)
        scene = Scene(config.screen_width, config.screen_height, targets=[target])

        warmup_frames = random.randint(1, 30)
        dt = 1.0 / config.fps
        for _ in range(warmup_frames):
            target.update(dt)
            vibration_offset_x, vibration_offset_y = vibration.update(dt)
            scene.render(scene_surface)
            camera_view = camera.get_view(
                scene_surface, vibration_offset_x, vibration_offset_y
            )
            camera_view = turbulence.apply(camera_view)
            camera_view = sensor_noise.apply(camera_view)

            local_x, local_y = camera.scene_to_local(
                target.x,
                target.y,
                vibration_offset_x,
                vibration_offset_y,
            )
            width, height = camera_view.get_size()
            if not (0 <= local_x < width and 0 <= local_y < height):
                continue

            split = "val" if random.random() < VAL_SPLIT else "train"
            image_name = f"frame_{saved:06d}.jpg"
            label_name = f"frame_{saved:06d}.txt"
            image_path = paths[f"images_{split}"] / image_name
            label_path = paths[f"labels_{split}"] / label_name

            bgr = surface_to_bgr(camera_view)
            cv2.imwrite(str(image_path), bgr)
            write_yolo_label(label_path, local_x, local_y, width, height)
            saved += 1
            if saved >= num_frames:
                break

    pygame.quit()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic beacon dataset")
    parser.add_argument(
        "--num-frames",
        type=int,
        default=DEFAULT_NUM_FRAMES,
        help="Number of labeled frames to generate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data",
        help="Output data directory",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    saved = generate_dataset(args.num_frames, args.output, seed=args.seed)
    print(f"Saved {saved} labeled frames to {args.output.resolve()}")
    if saved < args.num_frames:
        raise SystemExit(
            f"Requested {args.num_frames} frames but only generated {saved}"
        )


if __name__ == "__main__":
    main()
