# Performance evidence index (SIH26169)

Primary logs cited in the technical report and demo. Regenerate with the scripts below if needed.

## Matched-seed Classical vs AI (Benchmark Performance-1)

| Scenario | Classical CSV | AI CSV |
|---|---|---|
| Calm (turb0 vib0 noise0.05) | `classical_turb0_vib0_noise0.05.csv` | `ai_turb0_vib0_noise0.05.csv` |
| UAV (turb4 vib8 noise0.2) | `classical_turb4_vib8_noise0.2.csv` | `ai_turb4_vib8_noise0.2.csv` |
| Stress (turb7 vib15 noise0.35) | `classical_turb7_vib15_noise0.35.csv` | `ai_turb7_vib15_noise0.35.csv` |

Regenerate:

```bash
python scripts/run_comparison.py --duration 60
```

**Reported highlights (matched seed):** UAV lock Classical 97.7% → AI 100%; Stress re-acq Classical 2 → AI 1. Mean pixel error ≈35 px is largely slew-lag limited in physics mode.

## Acquisition Monte Carlo (`T_acq < 60 s` class)

| File | Result |
|---|---|
| `monte_carlo/acquisition_uav_40trials.json` | 40/40 pass; median ≈0.82 s |
| `monte_carlo/acquisition_stress_40trials.json` | 40/40 pass; median ≈0.97 s |

```bash
python scripts/monte_carlo_acquisition.py --trials 40 --scenario uav
python scripts/monte_carlo_acquisition.py --trials 40 --scenario stress
```

## Live session examples

| File | Notes |
|---|---|
| `run_2026-08-24_1027.csv` + `.summary.json` | Long interactive session with AI |
| `run_2026-08-24_1026.summary.json` | Additional session summary |

## Benchmark-2 (PTZ bypass)

Generate / score sample video:

```bash
python scripts/generate_ps_test_video.py
python scripts/benchmark_video.py --video logs/benchmark2/ps_sample.mp4 --gt logs/benchmark2/ps_sample_gt.csv
```

Outputs under `logs/benchmark2/` (centroid CSV + summary with `ptz_bypassed: true`). Sample Classical offline error ≈0.78 px avg / 0.86 px RMSE.

## Streamlit PDF

```bash
streamlit run report.py
```
