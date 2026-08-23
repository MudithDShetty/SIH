# SIH Problem Statement — Compliance & Winning Strategy

## Requirement checklist

| SIH requirement | Status | Evidence |
|---|---|---|
| Configurable virtual environment | **Partial** | Live sliders (`ui/controls.py`); scene presets hardcoded in `main.py` |
| One or more moving targets | **Partial** | `Scene` supports list; app runs one beacon |
| Movable virtual camera | **Done** | `VirtualCamera` with slew-rate-limited pointing |
| Automatic beacon detection | **Done** | Classical + YOLO (`detector/`) |
| Continuous CV tracking | **Done** | Kalman filter (`tracker/kalman_tracker.py`) |
| Camera control loop | **Done** | Detect → Kalman → `point_towards()` |
| Disturbances (turbulence, vibration, noise) | **Done** | `disturbance/disturbance.py` |
| Real-time performance display | **Done** | HUD + link readiness gauge (`main.py`) |
| AI-assisted tracking | **Done** | `AIDetector` (YOLOv8n) + training pipeline |
| Performance log / report | **Done** | CSV + JSON summary + Streamlit (`report.py`) |
| Classical vs AI comparison | **Done** | `scripts/run_comparison.py` + compare mode |
| Coarse-to-fine handoff signal | **Done** | Link Readiness Score (`docs/link_readiness.md`) |
| Re-acquisition (spiral search) | **Done** | `control/reacquisition.py` — aligns with literature spiral PAT |
| Standalone executable | **Partial** | `python main.py`; no `.exe` yet |
| Technical report / user manual | **Missing** | You must write these (10–15 pages + install guide) |
| 3–5 min demo video | **Missing** | Record using `docs/demo_checklist.md` |

**Core PAT loop: complete.** Gaps are packaging, documentation deliverables, and scientific polish.

---

## Parameters & Specifications table (standards-aligned)

Reference values from public space-optical standards and programs. Simulation uses pixel-domain equivalents where noted.

| Parameter | Literature / standard reference | Our simulation |
|---|---|---|
| PAT stages | Coarse (gimbal/camera) + fine (FSM/4-QD) — SDA OCT §2.1, ISRO OQC program | **Coarse stage implemented**; Link Readiness = handoff to fine (not simulated) |
| Acquisition FOV | ~2.5 mrad acquisition FOV (ESA IZN-1 ground station) | 400×300 px window ≈ configurable coarse FOV |
| Acquisition time target | &lt;60 s warm start (ESA ESTOL REQ-PHY-030); goal &lt;30 s | Spiral re-acquisition; log `avg_acquisition_time_s` in summary JSON |
| Closed-loop tracking error | &lt;2 µrad RMS fine stage (ESA IZN-1) | Pixel error + **angular error estimate** in HUD |
| Beam / beacon | 976 nm beacon, 0.3° divergence (ESA IZN-1 uplink beacon) | Warm yellow point source (~4 px) |
| Atmospheric effect | Beam wander, scintillation (Fried parameter r₀) | Image-domain turbulence warp (qualitative; not wave-optics) |
| Platform jitter | Gimbal / UAV vibration | AR(1) vibration model on camera position |
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
4. **Honest limits** — synthetic training data, qualitative turbulence, no real BER  
5. **Operational logging** — duration, FPS, max error, acquisition time, lock retention, processing time  

---

## Roadmap to win (priority order)

### Phase A — Submission blockers (this week)
1. Write **Technical Report** (architecture, formula, test methodology, honest AI comparison)
2. Write **User Manual** (install, controls, report.py)
3. Ship **`weights/beacon_yolov8n.pt`** in repo or clear train instructions
4. Record **3–5 min demo video**

### Phase B — Differentiators (high impact)
1. **Retrain YOLO** — 50+ epochs, harder disturbances in `generate_training_data.py`
2. **Angular error (µrad)** in HUD and logs — map pixel error via coarse FOV
3. **Preset scenarios** — “UAV mild”, “LEO turbulence”, “Acquisition stress” buttons
4. **PDF export** from Streamlit report for judges
5. **PyInstaller `.exe`** for “standalone application” deliverable

### Phase C — Scientist-grade (if time)
1. Fried-parameter-linked turbulence strength (r₀ → pixel wander σ)
2. Pan-tilt angles (azimuth/elevation) instead of pure x/y
3. Multi-beacon / multi-target scene
4. Fine-pointing sub-stage (4-QD mock) triggered when Link Readiness &gt; 0.7

---

## Latest benchmark (cite in report)

Settings: turbulence=4, vibration=8, sensor noise=0.2, 60 s, seed=42.

| Metric | Classical | AI |
|---|---|---|
| Avg pixel error | 35.1 px | 36.1 px |
| Lock retention | 98.3% | 100% |
| Re-acquisitions | 2 | 1 |

**Narrative:** AI improves lock stability; classical slightly better mean error under current 5-epoch weights. Retraining is the path to dominate both metrics.
