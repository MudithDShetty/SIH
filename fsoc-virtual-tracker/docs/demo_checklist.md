# Live Demo Checklist

Rehearse this mouse-only flow before judging. ~5 minutes.

## Demo video (recorded from real stack)

```bash
python scripts/record_demo_video.py --fps 15 --copy-site
```

Output: `logs/demo/beamlock_sih_demo.mp4` (also copied to `site/assets/` for Netlify).

Segments: title → Calm → UAV → Stress → forced lock-loss / raster re-acq → AI+fusion UAV → outro.

## Before the live demo

```bash
cd fsoc-virtual-tracker
.venv\Scripts\activate          # Windows
python scripts/smoke_test.py      # confirm nothing broken
```

Have `streamlit run report.py` ready in a second terminal with comparison CSVs loaded.

---

## Demo script (mouse only)

### 1. Baseline tracking (30 s)

```bash
python main.py
```

- Bottom panel: **Circular** trajectory, **Classical** detector
- Click **UAV** scenario (or press `F2`) — sets turb=4, vib=8, noise=0.2
- Point out: left overview + FOV box, right camera view, cyan crosshair (detector), magenta circle (Kalman)
- Top-right: **Link Readiness** gauge (green when locked and low error)

### 2. Disturbance response (20 s)

- Drag **Turbulence** up to ~7 → score drops, error rises
- Drag back to **4** → score recovers
- Say: score combines error, disturbances, and lock state (see `docs/link_readiness.md`)

### 3. Lock loss + re-acquisition (20 s)

- Press **`L`** (only keyboard shortcut needed) → detector blinded, tracking goes LOST
- Score hits **0**; orange spiral appears on left overview
- Wait for re-acquisition → score recovers, counter increments

### 4. Classical vs AI (30 s)

- Click **AI** in bottom panel (same sliders)
- Under moderate turbulence, AI should hold lower pixel error (check HUD line)
- If difference is small, say so honestly

### 5. Report evidence (1 min)

- Switch to browser: `streamlit run report.py`
- Enable **Compare two runs**
- Select `classical_turb4_vib8_noise0.2.csv` and `ai_turb4_vib8_noise0.2.csv`
- Show side-by-side summary cards and overlay charts

---

## If something breaks

| Problem | Fix |
|---|---|
| AI button reverts | Weights missing → run `python scripts/train.py` |
| Black camera view | Target left FOV — wait for spiral search or reduce disturbances |
| Streamlit empty | No CSV in `logs/` — run sim or `python scripts/run_comparison.py` |
| Low FPS with AI | Expected on CPU; classical demo still valid |

---

## Key talking points

1. **Closed loop:** detector → Kalman → camera slew (not cheating with ground truth)
2. **Link Readiness:** handoff heuristic, not BER — formula in `docs/link_readiness.md`
3. **Re-acquisition:** spiral search on LOST, automatic re-lock
4. **AI comparison:** real CSV numbers, honest if classical wins under light disturbance
