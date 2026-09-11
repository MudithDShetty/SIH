"""Detector package with lazy AI imports so classical mode avoids YOLO startup."""

from detector.classical_detector import ClassicalDetector
from detector.hybrid_detector import HybridDetector

__all__ = ["AIDetector", "ClassicalDetector", "HybridDetector"]


def __getattr__(name: str):
    if name == "AIDetector":
        from detector.ai_detector import AIDetector

        return AIDetector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
