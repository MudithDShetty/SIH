"""Detector package with lazy AI imports so classical mode avoids YOLO startup."""

from detector.classical_detector import ClassicalDetector

__all__ = ["AIDetector", "ClassicalDetector"]


def __getattr__(name: str):
    if name == "AIDetector":
        from detector.ai_detector import AIDetector

        return AIDetector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
