"""Build a standalone Windows executable with PyInstaller.

Usage (from repo root `fsoc-virtual-tracker/`):

    pip install pyinstaller
    python scripts/build_exe.py

Output: dist/FSOCVirtualTracker/FSOCVirtualTracker.exe

Notes:
  - Torch + Ultralytics make a large bundle (often 1–2+ GB). Prefer shipping
    the Python venv for demos if USB size is tight.
  - Weights are copied next to the exe when present.
  - This is a packaging convenience, not a certified flight binary.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_NAME = "FSOCVirtualTracker"
ENTRY = ROOT / "main.py"
WEIGHTS = ROOT / "weights" / "beacon_yolov8n.pt"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not installed. Run: pip install pyinstaller")
        return 1

    if not ENTRY.is_file():
        print(f"Missing entry point: {ENTRY}")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        DIST_NAME,
        "--paths",
        str(ROOT),
        "--collect-all",
        "ultralytics",
        "--collect-all",
        "torch",
        "--hidden-import",
        "cv2",
        "--hidden-import",
        "pygame",
        str(ENTRY),
    ]
    if WEIGHTS.is_file():
        # Keep weights beside the exe after build (also embed for one-folder).
        sep = ";" if sys.platform.startswith("win") else ":"
        cmd.extend(["--add-data", f"{WEIGHTS}{sep}weights"])

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    dist_dir = ROOT / "dist" / DIST_NAME
    weights_dst = dist_dir / "weights"
    weights_dst.mkdir(parents=True, exist_ok=True)
    if WEIGHTS.is_file():
        shutil.copy2(WEIGHTS, weights_dst / WEIGHTS.name)
        print(f"Copied weights -> {weights_dst / WEIGHTS.name}")

    exe = dist_dir / f"{DIST_NAME}.exe"
    if exe.is_file():
        print(f"OK: {exe}")
    else:
        print(f"Build finished; check {dist_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
