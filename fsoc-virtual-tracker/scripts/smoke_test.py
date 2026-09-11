#!/usr/bin/env python3
"""Headless smoke tests for fsoc-virtual-tracker."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


def test_report_imports_without_pygame() -> None:
    for module_name in list(sys.modules):
        if module_name == "pygame" or module_name.startswith("pygame."):
            del sys.modules[module_name]

    import importlib

    importlib.import_module("report")
    assert "pygame" not in sys.modules, "report.py should not import pygame"


def test_logger_round_trip() -> None:
    import pygame

    pygame.init()

    from metrics.logger import LogSnapshot, RunLogger
    from tracker.kalman_tracker import TRACKING_LOCKED

    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / "smoke.csv"
        logger = RunLogger(log_path)
        for _ in range(65):
            logger.record_frame(TRACKING_LOCKED, 1 / 60, 60.0, 4.0, 0.95)
            logger.maybe_log_second(
                LogSnapshot(
                    fps=60.0,
                    tracking_state=TRACKING_LOCKED,
                    pixel_error=4.0,
                    turbulence_strength=0.0,
                    vibration_amplitude=0.0,
                    sensor_noise_level=0.0,
                    link_readiness_score=0.95,
                    cumulative_lost_seconds=0.0,
                    reacquisition_count=0,
                    active_detector="classical",
                    angular_error_urad=25.0,
                    boresight_urad=20.0,
                    az_urad=10.0,
                    el_urad=-5.0,
                    pat_stage="COARSE",
                    handoff_count=0,
                )
            )
        logger.close()
        assert log_path.exists()
        csv_text = log_path.read_text(encoding="utf-8")
        assert len(csv_text.strip().splitlines()) >= 2, "expected header plus at least one data row"

    from report import load_run_csv, summarize_run

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as handle:
        handle.write(csv_text)
        saved_path = Path(handle.name)

    try:
        df = load_run_csv(saved_path)
        summary = summarize_run(df, saved_path.name)
        assert summary.row_count >= 1
        assert summary.active_detector == "classical"
    finally:
        saved_path.unlink(missing_ok=True)


def test_control_panel_apply() -> None:
    import pygame

    pygame.init()
    from disturbance import SensorNoiseModel, TurbulenceModel, VibrationModel
    from ui import CONTROL_PANEL_HEIGHT, ControlPanel

    screen = pygame.display.set_mode((1280, 720 + CONTROL_PANEL_HEIGHT))
    panel = ControlPanel(1280, 720)
    turb = TurbulenceModel(0.0)
    vib = VibrationModel(0.0)
    noise = SensorNoiseModel(0.0)

    class Camera:
        max_slew_rate = 90.0

    camera = Camera()
    panel.turbulence_slider.set_value(3.5)
    panel.apply_models(turb, vib, noise, camera)
    assert abs(turb.strength - 3.5) < 1e-6
    panel.draw(screen)
    pygame.quit()


def main() -> None:
    test_report_imports_without_pygame()
    test_logger_round_trip()
    test_control_panel_apply()
    print("All smoke tests passed.")


if __name__ == "__main__":
    main()
