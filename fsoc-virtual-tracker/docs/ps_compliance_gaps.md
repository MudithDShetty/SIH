# SIH26169 PS-table compliance (additive)

Official PDF parameters vs BeamLock dual-mode.

## Modes

| Mode | Launch | Purpose |
|---|---|---|
| Physics (default) | `python main.py` | Existing IZN-1 class FOV sandbox |
| PS Compliance | `python main.py --profile ps` | 2000×2000 screen, 640×480 FOV, 4°×3°, 5°/s slew, square 10×10 beacon |

## Benchmark Performance-2 (PTZ bypass)

```bash
python scripts/generate_ps_test_video.py
python scripts/benchmark_video.py --video logs/benchmark2/ps_sample.mp4 --gt logs/benchmark2/ps_sample_gt.csv
python scripts/benchmark_video.py --video logs/benchmark2/ps_sample.mp4 --detector ai --gt logs/benchmark2/ps_sample_gt.csv
```

Outputs under `logs/benchmark2/`: centroid CSV + summary JSON (`ptz_bypassed: true`).

## New controls (both modes)

| Key / UI | Action |
|---|---|
| `4` / Fig-8 button | Figure-of-8 trajectory (PS mandatory set of 4) |
| `N` | Cycle noise: legacy → gaussian → salt_pepper → poisson |
| `M` | Cycle weather: Clear → Haze → Fog → Rain → Low light |

## Still optional / packaging

- Build exe: `python scripts/build_exe.py`
- Lengthen demo video to 3–5 min when needed
