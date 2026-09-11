# SIH26169 — Team Cadets

**BeamLock** (package: `fsoc-virtual-tracker`) — AI-based virtual camera tracking for coarse alignment of mobile FSOC terminals.

## Deliverables

| Item | Path |
|---|---|
| Technical report | [`fsoc-virtual-tracker/docs/BeamLock_SIH_Technical_Report.pdf`](fsoc-virtual-tracker/docs/BeamLock_SIH_Technical_Report.pdf) |
| User manual | [`fsoc-virtual-tracker/docs/sih_user_manual.pdf`](fsoc-virtual-tracker/docs/sih_user_manual.pdf) |
| Performance logs | [`fsoc-virtual-tracker/logs/`](fsoc-virtual-tracker/logs/) |
| Executable build script | [`fsoc-virtual-tracker/scripts/build_exe.py`](fsoc-virtual-tracker/scripts/build_exe.py) |
| Windows EXE zip | [`fsoc-virtual-tracker/releases/BeamLock_FSOCVirtualTracker_Lite_Win64.zip`](fsoc-virtual-tracker/releases/BeamLock_FSOCVirtualTracker_Lite_Win64.zip) |


## Quick start

```bash
cd fsoc-virtual-tracker
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python main.py
```

Full install, GUI, and logging instructions: [`fsoc-virtual-tracker/README.md`](fsoc-virtual-tracker/README.md) and the [User Manual PDF](fsoc-virtual-tracker/docs/sih_user_manual.pdf).

Repository: https://github.com/MudithDShetty/SIH
