#!/usr/bin/env python3
"""One-time offline YOLO training for the beacon detector."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ultralytics import YOLO


def train(
    data_yaml: Path,
    model_name: str = "yolov8n.pt",
    epochs: int = 50,
    imgsz: int = 320,
    project: str = "runs/beacon",
    name: str = "train",
    weights_out: Path | None = None,
) -> Path:
    if not data_yaml.exists():
        raise FileNotFoundError(
            f"Dataset config not found: {data_yaml}. "
            "Run scripts/generate_training_data.py first."
        )

    model = YOLO(model_name)
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        project=project,
        name=name,
        verbose=True,
    )

    best_weights = Path(results.save_dir) / "weights" / "best.pt"
    if not best_weights.exists():
        raise FileNotFoundError(f"Training finished but weights not found: {best_weights}")

    output = weights_out or (ROOT / "weights" / "beacon_yolov8n.pt")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_weights, output)
    print(f"Copied best weights to {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLOv8 beacon detector")
    parser.add_argument(
        "--data",
        type=Path,
        default=ROOT / "data" / "data.yaml",
        help="Path to data.yaml",
    )
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument(
        "--weights-out",
        type=Path,
        default=ROOT / "weights" / "beacon_yolov8n.pt",
    )
    args = parser.parse_args()
    train(
        data_yaml=args.data,
        model_name=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        weights_out=args.weights_out,
    )


if __name__ == "__main__":
    main()
