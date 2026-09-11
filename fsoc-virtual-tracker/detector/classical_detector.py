import cv2
import numpy as np


class ClassicalDetector:
    """Baseline bright-spot detector using thresholding and contour centroids."""

    def __init__(
        self,
        brightness_threshold: int = 200,
        min_contour_area: float = 8.0,
    ) -> None:
        self.brightness_threshold = brightness_threshold
        self.min_contour_area = min_contour_area

    def detect(
        self,
        camera_view_bgr: np.ndarray,
        *,
        adaptive: bool = False,
    ) -> tuple[float, float] | None:
        if camera_view_bgr.size == 0:
            return None

        gray = cv2.cvtColor(camera_view_bgr, cv2.COLOR_BGR2GRAY)
        threshold = self.brightness_threshold
        if adaptive:
            peak = float(np.percentile(gray, 99.2))
            threshold = int(max(150, min(245, peak - 12)))

        _, mask = cv2.threshold(
            gray,
            threshold,
            255,
            cv2.THRESH_BINARY,
        )
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        largest_contour = None
        largest_area = self.min_contour_area
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_contour_area and area > largest_area:
                largest_area = area
                largest_contour = contour

        if largest_contour is None:
            return None

        moments = cv2.moments(largest_contour)
        if moments["m00"] == 0.0:
            return None

        centroid_x = moments["m10"] / moments["m00"]
        centroid_y = moments["m01"] / moments["m00"]
        return centroid_x, centroid_y

    def detect_all(
        self,
        camera_view_bgr: np.ndarray,
        *,
        adaptive: bool = False,
        max_detections: int = 8,
    ) -> list[tuple[float, float, float]]:
        """Return up to N centroids as (x, y, area), largest first."""
        if camera_view_bgr.size == 0:
            return []

        gray = cv2.cvtColor(camera_view_bgr, cv2.COLOR_BGR2GRAY)
        threshold = self.brightness_threshold
        if adaptive:
            peak = float(np.percentile(gray, 99.2))
            threshold = int(max(150, min(245, peak - 12)))

        _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates: list[tuple[float, float, float]] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < self.min_contour_area:
                continue
            moments = cv2.moments(contour)
            if moments["m00"] == 0.0:
                continue
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]
            candidates.append((float(cx), float(cy), area))

        candidates.sort(key=lambda item: item[2], reverse=True)
        return candidates[:max_detections]
