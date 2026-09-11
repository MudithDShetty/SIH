"""Hybrid AI + classical fusion detector for noisy FSOC beacon views."""

from __future__ import annotations

import math

from detector.ai_detector import AIDetector
from detector.classical_detector import ClassicalDetector
from detector.preprocess import preprocess_beacon_view


class HybridDetector:
    """YOLO + adaptive centroid fusion with denoise preprocessing.

    AI's advantage under noise comes from learning blob shape, but YOLO alone
    fails on out-of-distribution heavy grain. This pipeline:
      1. Denoise / top-hat enhance
      2. Run YOLO on raw + enhanced frames
      3. Run adaptive classical on enhanced frame
      4. Fuse by consensus (agreement) or best candidate
      5. Short temporal hold during re-acquisition gaps
    """

    HOLD_FRAMES = 8
    CONSENSUS_PX = 35.0

    def __init__(
        self,
        ai: AIDetector,
        classical: ClassicalDetector,
    ) -> None:
        self.ai = ai
        self.classical = classical
        self._hold: tuple[float, float] | None = None
        self._hold_frames = 0

    def detect(
        self,
        camera_view_bgr,
        *,
        noise_level: float = 0.0,
        reacquiring: bool = False,
    ) -> tuple[float, float] | None:
        if camera_view_bgr.size == 0:
            return self._maybe_hold(reacquiring)

        enhanced = preprocess_beacon_view(camera_view_bgr, noise_level)
        candidates: list[tuple[str, float, float, float]] = []

        for tag, frame, weight in (
            ("ai_enh", enhanced, 1.0),
            ("ai_raw", camera_view_bgr, 0.95),
        ):
            hit = self.ai.detect(frame, reacquiring=reacquiring)
            if hit is not None:
                candidates.append((tag, hit[0], hit[1], weight))

        for tag, frame, weight in (
            ("cls_enh", enhanced, 0.92),
            ("cls_raw", camera_view_bgr, 0.88),
        ):
            hit = self.classical.detect(frame, adaptive=True)
            if hit is not None:
                candidates.append((tag, hit[0], hit[1], weight))

        if not candidates:
            return self._maybe_hold(reacquiring)

        fused = self._fuse(candidates)
        self._hold = fused
        self._hold_frames = self.HOLD_FRAMES
        return fused

    def detect_all(
        self,
        camera_view_bgr,
        *,
        noise_level: float = 0.0,
        reacquiring: bool = False,
        max_detections: int = 8,
    ) -> list[tuple[float, float, float]]:
        """Multi-spot list for multi-beacon association (AI + classical union)."""
        if camera_view_bgr.size == 0:
            return []

        enhanced = preprocess_beacon_view(camera_view_bgr, noise_level)
        scored: list[tuple[float, float, float]] = []
        scored.extend(self.ai.detect_all(enhanced, reacquiring=reacquiring))
        scored.extend(self.ai.detect_all(camera_view_bgr, reacquiring=reacquiring))
        scored.extend(
            self.classical.detect_all(enhanced, adaptive=True, max_detections=max_detections)
        )
        scored.extend(
            self.classical.detect_all(
                camera_view_bgr, adaptive=True, max_detections=max_detections
            )
        )
        if not scored:
            return []

        # Greedy NMS by score so two beacons survive while duplicates collapse.
        scored.sort(key=lambda item: item[2], reverse=True)
        kept: list[tuple[float, float, float]] = []
        for cx, cy, score in scored:
            if any(math.hypot(cx - kx, cy - ky) <= self.CONSENSUS_PX for kx, ky, _ in kept):
                continue
            kept.append((cx, cy, score))
            if len(kept) >= max_detections:
                break
        return kept

    def _fuse(
        self,
        candidates: list[tuple[str, float, float, float]],
    ) -> tuple[float, float]:
        if len(candidates) == 1:
            return candidates[0][1], candidates[0][2]

        best_score = -1.0
        best_xy = (candidates[0][1], candidates[0][2])

        for i, (_, xi, yi, wi) in enumerate(candidates):
            support = 1.0
            for j, (_, xj, yj, wj) in enumerate(candidates):
                if i == j:
                    continue
                if math.hypot(xi - xj, yi - yj) <= self.CONSENSUS_PX:
                    support += wj
            score = wi * support
            if score > best_score:
                best_score = score
                best_xy = (xi, yi)

        return best_xy

    def _maybe_hold(self, reacquiring: bool) -> tuple[float, float] | None:
        if not reacquiring or self._hold is None or self._hold_frames <= 0:
            return None
        self._hold_frames -= 1
        return self._hold
