# SIH Problem Statement — Compliance & Winning Strategy

## Requirement checklist

| SIH requirement | Status | Evidence |
|---|---|---|
| Configurable virtual environment | **Done** | Sliders + Calm/UAV/Stress presets (`ui/scenarios.py`) |
| One or more moving targets | **Done** | Beacons 1/2 UI + `B` key; second beacon is a cooler distractor |
| Movable virtual camera | **Done** | `VirtualCamera` AZ/EL plant with rate/accel limits |
| Automatic beacon detection | **Done** | Classical + YOLO (`detector/`) |
| Continuous CV tracking | **Done** | Kalman filter (`tracker/kalman_tracker.py`) |
| Camera control loop | **Done** | Detect → Kalman → AZ/EL slew |
| Disturbances (turbulence, vibration, noise) | **Done** | Cn²→r₀ channel + AR(1) tip/tilt |
| Real-time performance display | **Done** | HUD (µrad primary) + link readiness gauge |
| AI-assisted tracking | **Done** | `AIDetector` / hybrid + training pipeline |
| Performance log / report | **Done** | CSV + run sheet JSON + Streamlit handoff timeline |
| Classical vs AI comparison | **Done** | `run_comparison.py` + `run_ablation.py` |
| Coarse-to-fine handoff signal | **Done** | Gated `FinePointingController` (stable frames) |
| Re-acquisition (spiral/raster search) | **Done** | Covariance-scaled search (`control/reacquisition.py`) |
| Acquisition Monte Carlo | **Done** | `scripts/monte_carlo_acquisition.py` vs ESTOL &lt;60 s |
| Clutter Pd/Pfa | **Done** | `scripts/evaluate_detection.py` |
| Standalone executable | **Done (script)** | `python scripts/build_exe.py` → PyInstaller one-folder |
| Technical report / user manual | **Draft** | `docs/technical_report.md`, `docs/user_manual.md`, `docs/beamlock_technical_deep_dive.pdf` |
| 3–5 min demo video | **Partial** | `logs/demo/beamlock_sih_demo.mp4` (~53 s); lengthen for optional deliverable |
| PS table dual-mode | **Done** | `python main.py --profile ps` (2000², 640×480, 4° FOV) |
| Figure-of-8 trajectory | **Done** | `4` / Fig-8 button |
| Named noise + weather | **Done** | `N` / `M` keys |
| Benchmark-2 MP4 PTZ bypass | **Done** | `scripts/benchmark_video.py` |

**Core PAT loop: complete.** Gaps are packaging, documentation deliverables, and scientific polish.

---

## Parameters & Specifications table (standards-aligned)

Reference values from public space-optical standards and programs. Simulation uses pixel-domain equivalents where noted.

| Parameter | Literature / standard reference | Our simulation |
|---|---|---|
| PAT stages | Coarse (gimbal/camera) + fine (FSM/4-QD) — SDA OCT §2.1, ISRO OQC program | **Coarse + fine mock** (`FinePointingController` handoff at readiness ≥ 0.7) |
| Acquisition FOV | ~2.5 mrad acquisition FOV (ESA IZN-1 ground station) | 400×300 px @ 2500 µrad → **IFOV 6.25 µrad/px** |
| Acquisition time target | &lt;60 s warm start (ESA ESTOL REQ-PHY-030); goal &lt;30 s | Spiral re-acquisition; log `avg_acquisition_time_s` in summary JSON |
| Closed-loop tracking error | &lt;2 µrad RMS fine stage (ESA IZN-1) | Pixel error + **true-IFOV angular error** in HUD |
| Beam / beacon | 976 nm beacon, 0.3° divergence (ESA IZN-1 uplink beacon) | Gaussian spot + link budget (`physics/link_budget.py`) |
| Atmospheric effect | Beam wander, scintillation (Fried parameter r₀) | Cn² proxy → r₀ / Rytov / wander / scintillation (`physics/atmosphere.py`) |
| Platform jitter | Gimbal / UAV vibration | AR(1) tip/tilt on FOV (px ↔ µrad via IFOV) |
| Detector | Centroid / deep learning (Photonics 2024 YOLO-PAT) | Classical threshold + YOLOv8n |
| Search pattern | Spiral scan (MDPI Photonics 11(6):540) | `ReacquisitionController` Archimedean spiral |
| Lock retention | PAT state machine (CCSDS / SDA OCT) | LOCKED / COASTING / LOST + `%` in logs |

**Honest limit:** There is no public ISRO PAT telemetry database to download. Credible approach: cite ISRO OQC/PAT architecture (TEC/ISRO presentations) and validate against ESA/SDA acquisition requirements in simulation.

---

## Evaluation criteria — how to score points

| Judge focus | Your strength | Action |
|---|---|---|
| Problem understanding | Two-stage PAT, disturbances, mobile platforms | Lead report with PAT diagram + standards table above |
| Working software | Full closed loop, live demo | Rehearse `docs/demo_checklist.md` |
| AI contribution | YOLO detector + comparison | **Report honestly:** classical won on mean error at turb=4; AI had higher LOCKED % |
| Performance analysis | CSV + Streamlit | Use `logs/classical_turb4_vib8_noise0.2.csv` vs `ai_*` |
| Innovation | Link Readiness Score | `docs/link_readiness.md` — emphasize handoff decision, not BER |
| Professionalism | UI + docs | JSON summary, angular error, scientist dashboard (next phase) |

---

## What “ISRO-grade” actually means here

Judges do **not** expect a flight-ready OCT. They expect:

1. **Physics-aware vocabulary** — mrad, PAT, coarse/fine, turbulence, acquisition cone  
2. **Traceable parameters** — table linked to SDA/ESA/ISRO public docs  
3. **Reproducible benchmarks** — matched-seed classical vs AI (`run_comparison.py`)  
4. **Honest limits** — synthetic training data, statistical (not wave-optics) channel, SNR handoff score ≠ BER  
5. **Operational logging** — duration, FPS, max error, acquisition time, lock retention, processing time  

---

## Roadmap to win (priority order)

### Phase A — Submission blockers (this week)
1. Write **Technical Report** (architecture, formula, test methodology, honest AI comparison)
2. Write **User Manual** (install, controls, report.py)
3. Ship **`weights/beacon_yolov8n.pt`** in repo or clear train instructions
4. Record **3–5 min demo video**

### Phase B — Differentiators
1. ~~Cn² → r₀ / wander / scintillation + Gaussian link SNR~~ **Done** (`physics/`)
2. ~~Fine-pointing mock after readiness &gt; 0.7~~ **Done** (`control/fine_pointing.py` + stable-frame gate)
3. ~~AZ/EL plant + µrad-primary logging~~ **Done** (`scene/camera.py`, CSV run sheet)
4. ~~Acquisition Monte Carlo vs ESTOL &lt;60 s~~ **Done** (`scripts/monte_carlo_acquisition.py`)
5. ~~Clutter Pd/Pfa~~ **Done** (`scripts/evaluate_detection.py`)
6. ~~Ablation summary~~ **Done** (`scripts/run_ablation.py`)
7. ~~**PDF export** from Streamlit report for judges~~ **Done** (`report.py` download)
8. ~~**PyInstaller `.exe`** for standalone deliverable~~ **Done** (`scripts/build_exe.py`)

### Phase C — Next physics / PAT upgrades
1. ~~Multi-beacon / multi-target scene~~ **Done** (Beacons 1/2 + association)
2. ~~Optional: noise on 4-QD channels / FSM latency~~ **Done** (`FinePointingController`)
3. Record demo video + finalize PDF report
---

## Latest benchmark (cite in report)

Pre-physics-upgrade matrix (hard curriculum, 50-epoch GPU). Re-run before claiming new physics-era numbers.

Settings: turbulence=4, vibration=8, sensor noise=0.2, seed=42.

| Metric | Classical | AI |
|---|---|---|
| Avg pixel error | 35.1 px | 36.1 px |
| Lock retention | 98.3% | 100% |
| Re-acquisitions | 2 | 1 |

**Narrative:** AI improves lock stability; mean error is largely slew-lag limited. Lead with lock / re-acq, not mean error alone.
