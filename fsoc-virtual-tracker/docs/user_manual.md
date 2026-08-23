# FSOC Virtual Tracker — User Manual

## 1. Overview

FSOC Virtual Tracker is a software simulation of **coarse pointing, acquisition, and tracking (PAT)** for free-space optical communication links between mobile platforms. It runs on Windows/Linux/macOS with Python 3.10+.

## 2. Installation

```bash
cd fsoc-virtual-tracker
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### AI detector weights (one-time)

```bash
python scripts/generate_training_data.py --num-frames 2400
python scripts/train.py --epochs 50 --imgsz 320
```

This creates `weights/beacon_yolov8n.pt`. Without it, the **AI** detector button will revert to Classical.

## 3. Running the application

```bash
python main.py
```

- Window size: **1280 × 880** (simulation + control panel)
- Exit: **ESC** or close window
- Logs: auto-written to `logs/run_YYYY-MM-DD_HHMM.csv` and `logs/run_*.summary.json`

## 4. User interface

### Main view (top)

| Region | Content |
|---|---|
| Left | Scene overview with camera FOV outline (green box) |
| Right | Live camera feed with disturbances applied |
| Top-left HUD | Camera position, detector, FPS, error (px + µrad), tracking state |
| Top-right | Link Readiness gauge (green ≥0.7, yellow 0.3–0.7, red <0.3) |

### Overlays on camera feed

| Symbol | Meaning |
|---|---|
| Cyan crosshair | Raw detector output |
| Magenta circle | Kalman filter estimate |
| Orange spiral (overview) | Re-acquisition search path when LOST |

### Control panel (bottom)

**Sliders:** Turbulence, Vibration, Sensor Noise, Slew Rate — drag to adjust live.

**Trajectory:** Linear / Circular / Random — beacon motion pattern.

**Detector:** Classical (threshold) / AI (YOLOv8).

**Scenario presets:** Calm / UAV / Stress — one-click disturbance bundles.

## 5. Keyboard shortcuts

| Key | Action |
|---|---|
| `1` / `2` / `3` | Trajectory: linear / circular / random walk |
| `Q` / `A` | Turbulence ±0.1 |
| `W` / `S` | Vibration ±0.5 |
| `E` / `D` | Sensor noise ±0.05 |
| `T` | Toggle Classical ↔ AI detector |
| `L` | Blind detector 60 frames (test re-acquisition) |
| `F1` | Scenario: Calm |
| `F2` | Scenario: UAV (benchmark) |
| `F3` | Scenario: Stress |
| `ESC` | Quit |

All parameters are also controllable with the mouse via the bottom panel.

## 6. Scenario presets

| Preset | Turbulence | Vibration | Noise | Use case |
|---|---|---|---|---|
| **Calm** | 0 | 0 | 0.05 | Baseline demo |
| **UAV** | 4 | 8 | 0.20 | Mobile platform benchmark |
| **Stress** | 7 | 15 | 0.35 | Acquisition stress test |

## 7. Performance report

```bash
streamlit run report.py
```

- Select a CSV from `logs/`
- Enable **Compare two runs** for classical vs AI evidence
- Use **Download report** for a text summary to attach to your submission

### Automated benchmark

```bash
python scripts/run_comparison.py --duration 60
```

Produces matched `classical_turb4_vib8_noise0.2.csv` and `ai_turb4_vib8_noise0.2.csv`.

## 8. Troubleshooting

| Issue | Solution |
|---|---|
| AI button reverts | Train weights (Section 2) |
| Low FPS with AI | Normal on CPU; use Classical for live demo |
| Black camera view | Reduce disturbances; wait for spiral re-acquisition |
| No logs | Run at least 1 second before quitting |

## 9. Verification

```bash
python scripts/smoke_test.py
```

All tests should print `All smoke tests passed.`
