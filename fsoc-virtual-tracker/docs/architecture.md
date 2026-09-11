# FSOC Virtual Tracker — Architecture

**Diagram (preferred):** open [`architecture.html`](architecture.html) in a browser.

Legacy PNG (optional): [`architecture.png`](architecture.png) via `python scripts/render_architecture.py`.
Mermaid source below matches the same topology.

```mermaid
flowchart TB
  subgraph INPUT["Operator / UI"]
    UI["Control Panel<br/>sliders · presets · Classical/AI · beacons"]
  end

  subgraph SCENE["Virtual World"]
    BEACON["Moving Beacon(s)"]
    CLUTTER["Stars / Glints"]
    CAM["Virtual Camera<br/>AZ/EL + FOV"]
    BEACON --> SCENE_RENDER["Scene Render"]
    CLUTTER --> SCENE_RENDER
    SCENE_RENDER --> CAM
  end

  subgraph CHANNEL["Disturbances + Physics"]
    TURB["Turbulence<br/>Cn² → wander / scintillation"]
    VIB["Platform Vibration"]
    NOISE["Sensor Noise"]
    LINK["Link Budget<br/>SNR / fade / pointing loss"]
  end

  subgraph DETECT["Detection"]
    CLASS["Classical<br/>threshold + centroid"]
    AI["YOLO AI"]
    HYB["Hybrid Fusion"]
    CLASS --> HYB
    AI --> HYB
  end

  subgraph TRACK["Tracking + Control"]
    KF["Kalman Tracker<br/>LOCKED / COASTING / LOST"]
    REACQ["Spiral Re-acquisition"]
    FINE["Fine Pointing Mock<br/>4-QD + FSM"]
    READY["Link Readiness Score"]
  end

  subgraph OUT["Outputs"]
    HUD["Live HUD µrad"]
    CSV["CSV + Run Sheet"]
    RPT["Streamlit Report / PDF"]
  end

  UI --> BEACON
  UI --> TURB
  UI --> VIB
  UI --> NOISE
  UI --> DETECT

  CAM --> TURB --> VIB --> NOISE --> DETECT
  CAM --> LINK
  DETECT --> KF
  KF -->|drive| CAM
  KF -->|LOST| REACQ --> CAM
  KF --> READY
  LINK --> READY
  READY -->|handoff| FINE --> CAM

  KF --> HUD
  KF --> CSV --> RPT
  READY --> HUD
```

## Stages

| Stage | What it does |
|---|---|
| Operator / UI | Sliders, presets, detector mode, beacon count |
| Virtual World | Beacons + clutter rendered into camera FOV |
| Disturbances + Physics | Turbulence, vibration, noise, link SNR / fade |
| Detection | Classical and/or YOLO → hybrid fusion |
| Tracking + Control | Kalman states, spiral re-acq, fine handoff |
| Outputs | HUD, CSV / run sheet, Streamlit report / PDF |

**Scope:** pointing, acquisition, tracking only. Not message transmission.
