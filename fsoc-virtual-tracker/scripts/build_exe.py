"""Build a standalone Windows executable with PyInstaller.

Usage (from ``fsoc-virtual-tracker/``):

    pip install pyinstaller
    python scripts/build_exe.py --lite     # shippable (~Classical; AI if Torch present)
    python scripts/build_exe.py            # full Torch+CUDA (often 4–5+ GB; not for GitHub)

Output: dist/FSOCVirtualTracker/FSOCVirtualTracker.exe

GitHub cannot host the full CUDA Torch bundle inside the git tree (100 MB file
limit; whole folder is multi-GB). Ship the **lite** zip via GitHub Releases.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_NAME = "FSOCVirtualTracker"
ENTRY = ROOT / "main.py"
WEIGHTS = ROOT / "weights" / "beacon_yolov8n.pt"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build BeamLock Windows executable")
    parser.add_argument(
        "--lite",
        action="store_true",
        help="Exclude Torch/Ultralytics/Streamlit (small zip for GitHub Releases). "
        "Classical mode always works; AI needs a full Python install or --full build.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Collect Torch + Ultralytics (very large; local USB demos only).",
    )
    args = parser.parse_args()
    lite = args.lite or not args.full

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
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--paths",
        str(ROOT),
        "--hidden-import",
        "cv2",
        "--hidden-import",
        "pygame",
        "--hidden-import",
        "filterpy",
        "--hidden-import",
        "numpy",
    ]

    if lite:
        # Separate folder so a locked full-build dist does not block the lite ship.
        cmd[cmd.index("--name") + 1] = f"{DIST_NAME}_Lite"
        dist_folder_name = f"{DIST_NAME}_Lite"
    else:
        dist_folder_name = DIST_NAME

    if lite:
        # Keep the onedir small enough to zip for GitHub Releases.
        for mod in (
            "torch",
            "torchvision",
            "ultralytics",
            "streamlit",
            "matplotlib",
            "pandas",
            "scipy",
            "pyarrow",
            "polars",
            "altair",
            "PIL",
        ):
            cmd.extend(["--exclude-module", mod])
        print("Building LITE executable (Classical path; no Torch bundled).")
    else:
        cmd.extend(
            [
                "--collect-all",
                "ultralytics",
                "--collect-all",
                "torch",
            ]
        )
        print("Building FULL executable (includes Torch; multi-GB).")

    if WEIGHTS.is_file():
        sep = ";" if sys.platform.startswith("win") else ":"
        cmd.extend(["--add-data", f"{WEIGHTS}{sep}weights"])

    cmd.append(str(ENTRY))
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    dist_dir = ROOT / "dist" / dist_folder_name
    weights_dst = dist_dir / "weights"
    weights_dst.mkdir(parents=True, exist_ok=True)
    if WEIGHTS.is_file():
        shutil.copy2(WEIGHTS, weights_dst / WEIGHTS.name)
        print(f"Copied weights -> {weights_dst / WEIGHTS.name}")

    # Ship a short README next to the exe for judges.
    readme = dist_dir / "README_EXE.txt"
    readme.write_text(
        "\n".join(
            [
                "BeamLock / FSOC Virtual Tracker — Windows executable",
                "SIH26169 · Team Cadets",
                "",
                f"Run:  {dist_folder_name}.exe",
                "Keep this folder intact (_internal/ must sit beside the .exe).",
                "",
                "This LITE build runs Classical detection fully.",
                "For AI (YOLO) hybrid mode, use: python main.py  (see repo README).",
                "",
                "Profiles: default Physics sandbox. For PS table mode use the Python entry:",
                "  python main.py --profile ps",
                "",
            ]
        ),
        encoding="utf-8",
    )

    exe = dist_dir / f"{dist_folder_name}.exe"
    if exe.is_file():
        print(f"OK: {exe}")
    else:
        print(f"Build finished; check {dist_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
