# FSOC Virtual Tracker

FSOC Virtual Tracker is a Python-based simulation and visualization framework for free-space optical communication (FSOC) beam tracking experiments. It provides a modular scaffold for scene rendering, disturbance modeling, target detection, tracking, control, metrics collection, and UI components.

## Virtual Environment Setup

```bash
cd fsoc-virtual-tracker
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python main.py
```

The window is 1280x852: a 1280x720 simulation viewport plus a bottom control panel for mouse-driven sliders and buttons. Press ESC or close the window to exit.

**Mouse controls (bottom panel):** turbulence, vibration, sensor noise, slew rate sliders; trajectory and detector buttons.

**Keyboard shortcuts (still work):** `1/2/3` (trajectory), `Q/A` `W/S` `E/D` (disturbances), `F1/F2/F3` (scenario presets), `L` (force lock loss), `T` (toggle Classical vs AI detector).

**Deliverables:** `docs/user_manual.md`, `docs/technical_report.md` (convert to PDF for submission).

## Performance Report

After a run, CSV logs are written to `logs/`. Open the Streamlit report (separate from `main.py`):

```bash
streamlit run report.py
```

Pick one log file for charts and summary stats, or enable **Compare two runs** for classical vs AI side-by-side evidence.

### Generate comparison evidence (recommended)

Matched classical vs AI runs with identical disturbance settings and per-frame RNG seeds:

```bash
python scripts/run_comparison.py --duration 60
```

Writes `logs/classical_turb4_vib8_noise0.2.csv` and `logs/ai_turb4_vib8_noise0.2.csv`.

See `docs/link_readiness.md` for the score formula and `docs/demo_checklist.md` for the live demo script.

See `docs/sih_compliance.md` for SIH requirement mapping, standards-aligned parameters, and winning strategy.


## AI Detector Training (One-Time Offline Step)

Generate synthetic labeled camera-view frames from the simulation pipeline:

```bash
python scripts/generate_training_data.py --num-frames 2400
```

This writes a YOLO dataset under `data/` with `images/train`, `images/val`, matching label files, and `data/data.yaml`.

Train YOLOv8n weights (not run live by `main.py`):

```bash
# CLI equivalent
yolo detect train data=data/data.yaml model=yolov8n.pt epochs=50 imgsz=320

# Or project helper script (copies best.pt to weights/beacon_yolov8n.pt)
python scripts/train.py --epochs 50 --imgsz 320
```

After training, `AIDetector` loads `weights/beacon_yolov8n.pt`. Press `T` in `main.py` to switch between `ClassicalDetector` and `AIDetector` at runtime.
