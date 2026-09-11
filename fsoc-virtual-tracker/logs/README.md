# Performance logs (SIH26169)

Automatic performance logging for BeamLock. Every interactive `python main.py` run writes:

| Artifact | Description |
|---|---|
| `run_YYYY-MM-DD_HHMM.csv` | Once-per-second time series |
| `run_*.runsheet.json` | Run config (profile, FOV, IFOV, handoff criteria) |
| `run_*.summary.json` | SIH aggregate metrics (`schema_version: sih26169-1.1`) |

Matched Classical vs AI evidence CSVs and Monte Carlo JSON also live here.

## SIH-required metrics (in `*.summary.json` → `sih_required`)

| Field | Meaning |
|---|---|
| `simulation_duration_s` | Total run duration |
| `fps` | Average frames per second |
| `tracking_error_px_avg` / `_max` | Tracking error in pixels |
| `tracking_error_urad_avg` / `_rms` | Angular error (µrad) via true IFOV |
| `lock_retention_pct` | Percent time LOCKED |
| `acquisition_time_s_avg` | Mean LOST → LOCK recovery time |
| `processing_time_ms_avg` / `_max` / `_p95` | Per-frame processing latency |
| `reacquisition_count` | Number of re-acquisition events |
| `active_detector` | `classical` or `ai` |

## CSV columns (time series)

`timestamp, fps, tracking_state, pixel_error, angular_error_urad, boresight_urad, az_urad, el_urad, pat_stage, handoff_count, turbulence_strength, vibration_amplitude, sensor_noise_level, link_readiness_score, cumulative_lost_seconds, reacquisition_count, active_detector`

## Curated evidence for judges

| File | What it shows |
|---|---|
| [`PERFORMANCE_INDEX.md`](PERFORMANCE_INDEX.md) | Index of primary evidence files |
| `classical_turb*_vib*_noise*.csv` / `ai_turb*_…` | Matched-seed Classical vs AI matrix |
| `monte_carlo/acquisition_uav_40trials.json` | Acquisition Monte Carlo (UAV) |
| `monte_carlo/acquisition_stress_40trials.json` | Acquisition Monte Carlo (Stress) |
| `run_*.summary.json` | Example live-session summaries |

## View / export

```bash
streamlit run report.py
```

Select a CSV, compare two runs, download PDF/TXT report.
