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

### Scenario matrix (45 s each, seed=42, 50-epoch GPU weights)

| Scenario | Settings | Classical err | AI err | Classical lock | AI lock | Winner |
|---|---|---|---|---|---|---|
| Calm | turb0 / vib0 / noise0.05 | 35.5 px | 35.5 px | 100% | 100% | Tie |
| UAV | turb4 / vib8 / noise0.2 | 35.6 px | 35.6 px | 97.7% | **100%** | AI (lock) |
| Stress | turb7 / vib15 / noise0.35 | **35.1 px** | 36.1 px | 95.5% | 95.5% | Classical (error) |

**Interpretation:** Mean pixel error is dominated by camera slew lag on the circular orbit (~35 px even in Calm), not detector noise. AI's real advantage at UAV is **lock retention**. Under Stress, classical still slightly wins mean error — and Stress (turb=7) is partly **out of distribution** for training (data generator used turb 0–5). Next upgrade: regenerate data with turb up to 8+, retrain, re-run Stress.

CSVs: `logs/classical_turb*_*.csv` and `logs/ai_turb*_*.csv`. Run matrix with:
```bash
python scripts/run_comparison.py --matrix --duration 45
```

