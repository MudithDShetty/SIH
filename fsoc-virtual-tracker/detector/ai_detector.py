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

    def detect(
        self,
        camera_view_bgr: np.ndarray,
        *,
        reacquiring: bool = False,
    ) -> tuple[float, float] | None:
        if camera_view_bgr.size == 0:
            return None

        conf = 0.15 if reacquiring else self.confidence_threshold
        results = self.model.predict(
            source=camera_view_bgr,
            conf=conf,
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
        if confidences[best_index] < conf:
            return None

        xyxy = boxes.xyxy.cpu().numpy()[best_index]
        centroid_x = (xyxy[0] + xyxy[2]) / 2.0
        centroid_y = (xyxy[1] + xyxy[3]) / 2.0
        return float(centroid_x), float(centroid_y)

    def detect_all(
        self,
        camera_view_bgr: np.ndarray,
        *,
        reacquiring: bool = False,
        max_detections: int = 8,
    ) -> list[tuple[float, float, float]]:
        """Return up to N centroids as (x, y, confidence), highest first."""
        if camera_view_bgr.size == 0:
            return []

        conf = 0.15 if reacquiring else self.confidence_threshold
        results = self.model.predict(
            source=camera_view_bgr,
            conf=conf,
            verbose=False,
            device=self.device,
        )
        if not results:
            return []

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return []

        confidences = boxes.conf.cpu().numpy()
        xyxy = boxes.xyxy.cpu().numpy()
        candidates: list[tuple[float, float, float]] = []
        for index, score in enumerate(confidences):
            if float(score) < conf:
                continue
            box = xyxy[index]
            cx = (box[0] + box[2]) / 2.0
            cy = (box[1] + box[3]) / 2.0
            candidates.append((float(cx), float(cy), float(score)))

        candidates.sort(key=lambda item: item[2], reverse=True)
        return candidates[:max_detections]
