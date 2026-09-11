"""Fast preprocessing for beacon detection under sensor noise."""

from __future__ import annotations

import cv2
import numpy as np


def preprocess_beacon_view(
    bgr: np.ndarray,
    noise_level: float = 0.0,
) -> np.ndarray:
    """Enhance bright beacon blobs on a dark background.

    Pipeline inspired by low-SNR star/beacon papers: median denoise +
    morphological top-hat to lift point sources above background.
    """
    if bgr.size == 0:
        return bgr

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    if noise_level > 0.05:
        k = 5 if noise_level > 0.35 else 3
        gray = cv2.medianBlur(gray, k)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    enhanced = cv2.add(gray, (tophat * (1.0 + noise_level * 2.0)).astype(np.uint8))

    # Mild gamma lift for very dark noisy frames.
    if noise_level > 0.25:
        lut = np.array(
            [((i / 255.0) ** 0.75) * 255 for i in range(256)],
            dtype=np.uint8,
        )
        enhanced = cv2.LUT(enhanced, lut)

    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
