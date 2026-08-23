# Link Readiness Score

Decision-support heuristic for **coarse-to-fine FSOC handoff**. Answers whether coarse beacon tracking is good enough to attempt fine pointing / link closure.

**This is not** a BER model, outage probability, or certified link budget.

Implementation: `metrics/link_readiness.py`

---

## Inputs (per frame)

| Input | Source | Range |
|---|---|---|
| `pixel_error` | `hypot(kalman_x - beacon_x, kalman_y - beacon_y)` in scene px | 0 → ∞ |
| `turbulence_strength` | `TurbulenceModel.strength` | 0 – 10 |
| `vibration_amplitude` | `VibrationModel.amplitude` | 0 – 50 |
| `tracking_state` | Kalman tracker | `LOCKED` / `COASTING` / `LOST` |

**Not in v1 formula:** sensor noise (logged to CSV only; affects detection indirectly via pixel error).

**Error reference:** `min(fov_width, fov_height)` → default **300 px** (400×300 camera FOV).

---

## Sub-scores (each ∈ [0, 1])

### 1. Pixel error (weight 0.40)

```
normalized_error = clamp(pixel_error / error_reference, 0, 1)
pixel_error_subscore = 1 - normalized_error
```

Tracking error is the primary observable for coarse pointing. Normalizing by FOV scale makes the score portable across camera configs.

### 2. Turbulence (weight 0.20)

```
turbulence_subscore = 1 - clamp(turbulence_strength / 10.0, 0, 1)
```

Higher turbulence degrades image quality and detection stability before fine-pointing handoff.

### 3. Vibration (weight 0.20)

```
vibration_subscore = 1 - clamp(vibration_amplitude / 50.0, 0, 1)
```

Platform jitter moves the FOV independently of tracker belief; penalized even when nominally LOCKED.

### 4. Tracking state (weight 0.20)

```
LOCKED    → 1.0
COASTING  → 0.35
LOST      → 0.0  (see hard rule)
```

COASTING means missed detections; the filter is extrapolating. 0.35 is partial credit, not a physical constant.

---

## Final score

**Hard rule:** `tracking_state == LOST` → **score = 0.0** (no handoff when coarse lock is lost).

**Otherwise:**

```
score = clamp(
    0.40 × pixel_error_subscore
  + 0.20 × turbulence_subscore
  + 0.20 × vibration_subscore
  + 0.20 × tracking_state_subscore,
  0, 1
)
```

---

## UI thresholds (`main.py`)

| Score | Gauge color | Demo label |
|---|---|---|
| ≥ 0.7 | Green | Ready |
| 0.3 – 0.7 | Yellow | Marginal |
| < 0.3 | Red | Not ready |

Demo conventions only — not derived from optical theory.

---

## Worked example

No disturbances, LOCKED, 36 px error, FOV reference 300 px:

- `pixel_error_subscore = 1 - 36/300 = 0.88`
- Other subscores = 1.0
- `score = 0.40×0.88 + 0.20 + 0.20 + 0.20 = 0.952`

---

## One-liner for judges

> Weighted 0–1 coarse-tracking handoff readiness: 40% normalized pixel error, 40% disturbance severity (turbulence + vibration), 20% lock-state confidence, hard zero on LOST — a decision-support signal, not a physical BER model.

---

## Evidence

Generate paired classical vs AI logs with matched disturbances:

```bash
python scripts/run_comparison.py --duration 60
```

Compare in `streamlit run report.py` using the `classical_turb4_vib8_noise0.2.csv` and `ai_turb4_vib8_noise0.2.csv` files.

### Latest benchmark (turb=4, vib=8, noise=0.2, 60 s, seed=42)

| Metric | Classical | AI |
|---|---|---|
| Avg pixel error | 35.1 px | 36.1 px |
| Avg link readiness | 0.839 | 0.840 |
| % LOCKED | 98.3% | 100.0% |
| Re-acquisitions | 2 | 1 |

Under these moderate-disturbance settings, classical thresholding slightly outperformed the 5-epoch YOLO model on mean pixel error. AI spent more time LOCKED and re-acquired once fewer time. Report both metrics — the comparison is still credible evidence of a rigorous evaluation.
