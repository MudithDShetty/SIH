# FSOC Virtual Tracker — Technical Report (Draft)

**Team:** [Your team name]  
**Problem:** SIH — AI-assisted coarse PAT for FSOC mobile links  
**Version:** 1.0

---

## 1. Problem understanding

Free-Space Optical Communication (FSOC) enables gigabit-to-terabit data rates using narrow laser beams. Before a fine-pointing stage (fast steering mirror, quadrant detector) can close the link, a **coarse alignment stage** must:

1. Observe the scene via a wide-field camera  
2. Detect the remote beacon  
3. Estimate its position  
4. Continuously slew the camera/gimbal to keep the beacon in FOV  

Hardware PAT development requires expensive optics, gimbals, and test ranges. This project provides a **software virtual camera** for algorithm development, classical vs AI detector comparison, and quantitative performance logging.

### Standards context

Our parameters align with public references:

- **SDA OCT Standard v3.0.1** — PAT state machine, lead/follow acquisition  
- **ESA ESTOL** — acquisition time targets (&lt;60 s warm start)  
- **ESA IZN-1 ground station** — ~2.5 mrad acquisition FOV, µrad-class fine tracking  
- **ISRO Opto-Quantum Communication program** — gimbal + fine pointing PAT architecture (TEC/ISRO presentations)

We do **not** claim flight qualification or BER certification.

---

## 2. System architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│ Virtual     │───▶│ Disturbances │───▶│  Detector   │───▶│ Kalman       │
│ Scene+Camera│    │ turb/vib/noise│   │ Class. / AI │    │ Tracker      │
└─────────────┘    └──────────────┘    └─────────────┘    └──────┬───────┘
       ▲                                                          │
       │              ┌──────────────┐    ┌─────────────┐         │
       └──────────────│ Camera slew  │◀───│ Re-acq spiral│◀── LOST
                      │ (rate-limited)│    │  search      │
                      └──────────────┘    └─────────────┘
                              │
                      ┌───────▼────────┐
                      │ Link Readiness │──▶ coarse-to-fine handoff signal
                      │ Score (0–1)    │
                      └────────────────┘
```

### Module map

| Module | File | Role |
|---|---|---|
| Scene | `scene/scene.py` | Beacon motion (linear/circular/random walk) |
| Camera | `scene/camera.py` | FOV crop, slew-rate limit, angular error |
| Disturbances | `disturbance/disturbance.py` | Turbulence warp, vibration AR(1), sensor noise |
| Classical detector | `detector/classical_detector.py` | Threshold + contour centroid |
| AI detector | `detector/ai_detector.py` | YOLOv8n bounding-box centroid |
| Tracker | `tracker/kalman_tracker.py` | Constant-velocity Kalman, LOCKED/COASTING/LOST |
| Re-acquisition | `control/reacquisition.py` | Archimedean spiral search (literature-standard) |
| Link readiness | `metrics/link_readiness.py` | Weighted handoff heuristic |
| Logger | `metrics/logger.py` + `session_metrics.py` | CSV + JSON SIH metrics |
| UI | `ui/controls.py` | Sliders, presets, detector/trajectory buttons |
| Report | `report.py` | Streamlit analysis and comparison |

---

## 3. Tracking methods

### 3.1 Detection

**Classical:** Grayscale threshold (default 200) → largest contour centroid. Baseline for bright beacon on dark sky.

**AI:** YOLOv8n trained on 2400 synthetic frames from the same disturbance pipeline. Returns highest-confidence box centroid.

### 3.2 Estimation

4-state constant-velocity Kalman filter (filterpy). States: x, y, vx, vy.

| State | Condition |
|---|---|
| LOCKED | Valid detection this frame |
| COASTING | 1–15 consecutive missed frames |
| LOST | &gt;15 misses; spiral search activated |

Camera is driven by **Kalman estimate**, not ground truth.

### 3.3 Re-acquisition

On LOST, `ReacquisitionController` generates a spiral waypoint sequence biased along last known velocity (MDPI Photonics 11(6):540 spiral acquisition pattern). Camera slews at `max_slew_rate` until detector re-locks.

---

## 4. AI methods

1. **Synthetic data:** `scripts/generate_training_data.py` — varied turbulence, vibration, noise, trajectories  
2. **Training:** `scripts/train.py` — YOLOv8n, 320×320, copies best weights to `weights/beacon_yolov8n.pt`  
3. **Runtime:** Lazy-loaded `AIDetector` — same API as classical  

### Honest comparison — scenario matrix after hard curriculum

Training data regenerated to turb **0–8.5**, vib **0–25**, noise **0–0.75** (3000 frames), then 50-epoch GPU retrain. Matrix re-run (45 s, seed=42):

| Scenario | Classical err | AI err | Classical lock | AI lock | Reacq C/AI |
|---|---|---|---|---|---|
| Calm | 35.5 px | 35.5 px | 100% | 100% | 1 / 1 |
| UAV | 35.6 px | 35.6 px | 97.7% | **100%** | 1 / 1 |
| Stress | **35.1 px** | 36.1 px | 95.5% | 95.5% | 2 / **1** |

**Interpretation:** Mean pixel error is largely slew-lag limited (~35 px even in Calm), so it does not clearly separate detectors. AI improves **lock retention** under UAV and **reduces re-acquisitions** under Stress. Report that tradeoff honestly — do not claim Stress mean-error superiority the data does not support.

---

## 5. Link Readiness Score (novelty)

Weighted 0–1 heuristic for **coarse-to-fine handoff** decision support:

```
score = 0.40×(1 - error/ref) + 0.20×(1 - turb/10) + 0.20×(1 - vib/50) + 0.20×state_factor
LOST → score = 0
```

See `docs/link_readiness.md` for full derivation. **Not a BER model.**

---

## 6. Test methodology

1. **Scenario presets:** Calm, UAV, Stress (`ui/scenarios.py`)  
2. **Matched-seed benchmark:** `scripts/run_comparison.py`  
3. **Metrics logged:** duration, FPS, pixel error, max error, lock retention %, acquisition time, processing time, re-acquisitions  
4. **Visualization:** `streamlit run report.py`  

---

## 7. Performance analysis

[Insert screenshots from Streamlit compare mode]

Session summary JSON example fields:
- `max_pixel_error_px`
- `lock_retention_pct`
- `avg_acquisition_time_s`
- `avg_processing_time_ms`

---

## 8. Limitations

- Turbulence is image-domain warp, not wave-optics / Fried parameter propagation  
- Single beacon in runtime (multi-target architecture exists)  
- 2D camera translation, not full gimbal azimuth/elevation  
- AI trained on synthetic data only  
- No physical link budget or BER  

---

## 9. Future improvements

1. Fried-parameter-linked turbulence (r₀ → pixel wander σ)  
2. Pan-tilt angle state with µrad telemetry  
3. Fine-pointing sub-stage mock (4-QD when readiness &gt; 0.7)  
4. Multi-beacon scenes  
5. PyInstaller standalone executable  
6. Extended YOLO training on GPU  

---

## 10. References

1. SDA Optical Communications Terminal Standard v3.0.1  
2. ESA ESTOL air interface v2.2 (REQ-PHY-030 acquisition time)  
3. ESA IZN-1 Direct-to-Earth optical communications (EPIC 2024)  
4. MDPI Photonics 11(6):540 — Optimal spiral scanning for FSO acquisition  
5. Applied Optics 2024 — Deep vision YOLO FSO-PAT system  
6. ISRO Opto-Quantum Communication program overview (TEC)

---

*Convert this document to PDF for submission. Add team name, screenshots, and institution logo.*
