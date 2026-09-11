# BeamLock — FSOC Virtual Tracker

**SIH26169** · Team **Cadets** · Department of Space / ISRO · Smart Automation / Space Technology  
AI-based virtual camera tracking for **coarse alignment** of mobile free-space optical (FSOC) terminals.

Real-time software PAT sandbox: virtual scene + AZ/EL camera, Classical / hybrid-AI detection, Kalman tracking, raster re-acquisition, Cn² channel + link readiness, optional Fine 4-QD mock, and automatic performance logs.

> Not a certified BER model, phase-screen propagator, or flight-qualified optical terminal.

---

## Deliverables (start here)

| Deliverable | Link |
|---|---|
| **Technical report (PDF)** | [`docs/BeamLock_SIH_Technical_Report.pdf`](docs/BeamLock_SIH_Technical_Report.pdf) |
| **User manual (PDF)** | [`docs/sih_user_manual.pdf`](docs/sih_user_manual.pdf) |
| **Performance logs** | [`logs/`](logs/) · [README](logs/README.md) · [Evidence index](logs/PERFORMANCE_INDEX.md) |
| **Executable (Windows zip)** | [`releases/BeamLock_FSOCVirtualTracker_Lite_Win64.zip`](releases/BeamLock_FSOCVirtualTracker_Lite_Win64.zip) · [notes](releases/README.md) |
| **Executable (build script)** | [`scripts/build_exe.py`](scripts/build_exe.py) (`--lite` for shippable; `--full` for local Torch) |
| **Source code** | this repository (`fsoc-virtual-tracker/`) — modular packages, documented entry points |
| **Browser / judge site** | [`site/`](site/) (Netlify static demo) |
| **Report figures** | [`docs/figures/`](docs/figures/) |

---

## Download and use

### 1. Get the code

```bash
git clone https://github.com/MudithDShetty/SIH.git
cd SIH/fsoc-virtual-tracker
```

Or download the ZIP from GitHub → **Code → Download ZIP**, then open `fsoc-virtual-tracker/`.

### 2. Install (Python 3.10+)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Optional NVIDIA CUDA Torch (faster AI):

```bash
pip uninstall -y torch torchvision
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

AI weights ship at `weights/beacon_yolov8n.pt`. If missing, see User Manual § installation / training.

### 3. Run the desktop app

```bash
python main.py                  # Physics profile (default sandbox)
python main.py --profile ps     # SIH Parameters-table geometry
```

- **ESC** or close window to exit  
- Logs written to `logs/run_*.csv` + `.summary.json` + `.runsheet.json`  
- Full GUI / keyboard guide: [User Manual PDF](docs/sih_user_manual.pdf)

### 4. View performance report

```bash
streamlit run report.py
```

Pick a CSV from `logs/`, compare Classical vs AI, download PDF/TXT.

### 5. Windows `.exe` (download)

Download [`releases/BeamLock_FSOCVirtualTracker_Lite_Win64.zip`](releases/BeamLock_FSOCVirtualTracker_Lite_Win64.zip), unzip, run `FSOCVirtualTracker_Lite.exe`.

Or rebuild:

```bash
pip install pyinstaller
python scripts/build_exe.py --lite
```

Lite = Classical path (GitHub-sized). Full Torch+CUDA (`--full`) is multi-GB and is for local USB demos only, not the git tree.

### 6. Browser mini-demo (judges)

Static site (does **not** run the full Pygame stack):

```bash
cd site
python -m http.server 8080
```

Open `http://localhost:8080`. Netlify publish dir is `site/` (see root / package `netlify.toml`).

---

## Quick controls

| Input | Action |
|---|---|
| Sliders | Cn² proxy, vibration, sensor noise, slew rate |
| Buttons | Trajectory (incl. Fig-8), Classical/AI, beacons 1/2, Calm/UAV/Stress |
| `1`–`4` | Trajectories (4 = figure-8) |
| `T` / `B` / `L` | Detector toggle / beacons / force blind (re-acq test) |
| `N` / `M` | Noise type / weather grade |
| `F1`–`F3` | Calm / UAV / Stress |

---

## Repository layout

```
fsoc-virtual-tracker/
  main.py              # Live closed-loop application
  config.py / profiles.py
  scene/               # Beacons + virtual camera
  physics/             # Atmosphere + link budget
  disturbance/         # Turbulence / vibration / noise / weather
  detector/            # Classical, YOLO, hybrid fusion
  tracker/             # Kalman + LOCKED/COASTING/LOST
  control/             # Raster re-acq + Fine handoff mock
  metrics/             # Link readiness + CSV/JSON logging
  ui/                  # Control panel + presets
  scripts/             # Comparison, Monte Carlo, Benchmark-2, EXE, demo video
  docs/                # Judge PDFs + figures (technical report, user manual)
  logs/                # Performance evidence
  site/                # Browser landing / mini-demo
  weights/             # YOLO beacon weights
```

Packages include module docstrings; key algorithms are commented at control/physics/detector boundaries.

---

## Evaluation helpers

```bash
python scripts/smoke_test.py
python scripts/run_comparison.py --duration 60
python scripts/monte_carlo_acquisition.py --trials 40 --scenario uav
python scripts/benchmark_video.py --video logs/benchmark2/ps_sample.mp4 --gt logs/benchmark2/ps_sample_gt.csv
python scripts/record_demo_video.py --fps 15 --copy-site
```

Compliance and demo notes live in the technical report PDF and [`logs/PERFORMANCE_INDEX.md`](logs/PERFORMANCE_INDEX.md).

---

## License / scope

Software prototype for SIH26169 algorithm development and evaluation. Physics models are statistical (Andrews-style order-of-magnitude), not flight certification.
