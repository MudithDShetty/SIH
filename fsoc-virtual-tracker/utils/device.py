"""CUDA / CPU device selection for YOLO inference and training."""


def yolo_device() -> int | str:
    try:
        import torch
    except ImportError:
        return "cpu"
    return 0 if torch.cuda.is_available() else "cpu"


def device_label() -> str:
    device = yolo_device()
    if device == "cpu":
        return "cpu"
    try:
        import torch

        return f"cuda ({torch.cuda.get_device_name(0)})"
    except Exception:
        return "cuda"
