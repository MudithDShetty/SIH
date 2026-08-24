from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from utils.device import device_label, yolo_device

DEFAULT_WEIGHTS = Path(__file__).resolve().parents[1] / "weights" / "beacon_yolov8n.pt"


class AIDetector:
    """YOLOv8-based beacon detector with ClassicalDetector-compatible API."""

    def __init__(
        self,
        weights_path: str | Path | None = None,
        confidence_threshold: float = 0.25,
    ) -> None:
        self.weights_path = Path(weights_path or DEFAULT_WEIGHTS)
        self.confidence_threshold = confidence_threshold
        if not self.weights_path.exists():
            raise FileNotFoundError(
                f"AI detector weights not found: {self.weights_path}. "
                "Run scripts/train.py after generating data."
            )
        self.model = YOLO(str(self.weights_path))
        self.device = yolo_device()
        print(f"AIDetector using {device_label()}")

    def detect(self, camera_view_bgr: np.ndarray) -> tuple[float, float] | None:
        if camera_view_bgr.size == 0:
            return None

        results = self.model.predict(
            source=camera_view_bgr,
            conf=self.confidence_threshold,
            verbose=False,
            device=self.device,
        )
        if not results:
            return None

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return None

        confidences = boxes.conf.cpu().numpy()
        best_index = int(np.argmax(confidences))
        if confidences[best_index] < self.confidence_threshold:
            return None

        xyxy = boxes.xyxy.cpu().numpy()[best_index]
        centroid_x = (xyxy[0] + xyxy[2]) / 2.0
        centroid_y = (xyxy[1] + xyxy[3]) / 2.0
        return float(centroid_x), float(centroid_y)
