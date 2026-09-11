# Windows executable

**File:** [BeamLock_FSOCVirtualTracker_Lite_Win64.zip](BeamLock_FSOCVirtualTracker_Lite_Win64.zip) (~79 MB)

1. Download and unzip.
2. Run `FSOCVirtualTracker_Lite.exe` (keep `_internal/` beside it).
3. Classical detection works fully in this build.
4. For AI (YOLO) hybrid mode, use `python main.py` from the repo (full Torch bundle is multi-GB and cannot live in git).

Rebuild: `python scripts/build_exe.py --lite`
