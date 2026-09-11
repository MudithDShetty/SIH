# Link Readiness Score

Decision-support score for **coarse-to-fine FSOC handoff**. Answers whether coarse beacon tracking is good enough to attempt fine pointing / link closure.

**This is not** a certified BER, outage probability, or flight-qualified link budget. v2 is physics-informed (SNR / fade margin) when the optical link model is active.

Implementation: `metrics/link_readiness.py` · channel: `physics/atmosphere.py` · budget: `physics/link_budget.py`

---

## Physics path (default in `main.py`)

Each frame:

1. UI **Cn2 proxy** (0–10) → log-uniform Cn² → Fried `r₀`, Rytov variance
2. Beam wander (µrad) + scintillation irradiance `I`
3. Boresight residual → pointing loss on a Gaussian acquisition beam
4. `OpticalLink` → `P_rx`, SNR (dB), fade margin vs 10 dB handoff floor
5. Readiness blend:

```
score = clamp(
    0.45 × snr_subscore          # 10 dB → 0, 25 dB → 1
  + 0.25 × pointing_loss
  + 0.15 × min(1, scintillation)
  + 0.15 × lock_state_subscore,
  0, 1
)
```

**Hard rule:** `LOST` → score = 0.

HUD shows SNR, fade margin, Cn², `r₀`, and `I`.

---

## Fine stage handoff (4-QD mock)

When readiness ≥ **0.70**, tracking is **LOCKED**, and boresight residual ≤ **600 µrad**, control hands off to `FinePointingController` (`control/fine_pointing.py`):

- Mock **4-quadrant** signals from spot vs FOV center
- High-bandwidth FSM tip/tilt nulling (~4000 µrad/s)
- Exit if readiness &lt; **0.55**, COASTING/LOST, or residual &gt; 900 µrad

HUD shows `PAT: FINE 4QD` with residual and quad `(qx, qy)`. Camera view draws the FOV-center cross and quad bars.

Still a demo plant, not a calibrated flight FSM / 4-QD model.

---

## Fallback heuristic (no SNR supplied)

| Input | Range |
|---|---|
| `pixel_error` | scene px |
| `turbulence_strength` | 0 – 10 (Cn² proxy) |
| `vibration_amplitude` | 0 – 50 px tip/tilt |
| `tracking_state` | LOCKED / COASTING / LOST |

```
score = 0.40×err + 0.20×turb + 0.20×vib + 0.20×lock
```

---

## Angular camera

`VirtualCamera` exposes true IFOV:

```
IFOV_urad = FOV_horizontal_urad / fov_width
# default: 2500 µrad / 400 px = 6.25 µrad/px (ESA IZN-1 class FOV scale)
```

Pixel error → µrad via IFOV. Slew rate is shown as px/s and µrad/s.

---

## UI thresholds

| Score | Color | Label |
|---|---|---|
| ≥ 0.7 | Green | Ready |
| 0.3 – 0.7 | Yellow | Marginal |
| < 0.3 | Red | Not ready |

Demo conventions — not optical theory constants.

---

## One-liner for judges

> Physics-informed coarse-to-fine handoff score from Cn²-driven scintillation / beam wander, Gaussian-beam pointing loss, and SNR fade margin — a decision-support signal, not a certified BER model.

---

## Evidence

```bash
python scripts/run_comparison.py --duration 60
```

Compare in `streamlit run report.py`.

### Scenario matrix after hard curriculum (pre-physics-upgrade baseline)

| Scenario | Classical err | AI err | Classical lock | AI lock | Reacq C/AI | Winner |
|---|---|---|---|---|---|---|
| Calm | 35.5 px | 35.5 px | 100% | 100% | 1 / 1 | Tie |
| UAV | 35.6 px | **35.6 px** | 97.7% | **100%** | 1 / 1 | AI (lock) |
| Stress | **35.1 px** | 36.1 px | 95.5% | 95.5% | 2 / **1** | Mixed |

**Honest takeaway:** Mean pixel error is largely slew-lag limited. AI value is lock retention / fewer re-acquisitions. Re-run the matrix after this physics upgrade before citing new numbers.
