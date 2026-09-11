"""Detailed PAT architecture — orthogonal wires in gutters only, no floating stubs."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "architecture.png"

W, H = 2200, 1750
BG = (252, 253, 255)
INK = (22, 36, 54)
MUTED = (95, 110, 130)
TEAL = (40, 105, 140)
ORANGE = (170, 85, 30)
ACCENT = (0, 110, 120)

FILL = {
    "ui": (230, 240, 250),
    "scene": (232, 245, 240),
    "chan": (245, 238, 230),
    "det": (238, 232, 248),
    "track": (232, 240, 250),
    "out": (245, 245, 238),
}
EDGE = {
    "ui": (70, 110, 160),
    "scene": (40, 130, 100),
    "chan": (170, 110, 50),
    "det": (110, 80, 160),
    "track": (50, 100, 160),
    "out": (120, 120, 70),
}


def font(size: int, bold: bool = False):
    for name in (["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]):
        p = Path("C:/Windows/Fonts") / name
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def C(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def T(b):
    return (b[0] + b[2]) / 2, b[1]


def B(b):
    return (b[0] + b[2]) / 2, b[3]


def L(b):
    return b[0], (b[1] + b[3]) / 2


def R(b):
    return b[2], (b[1] + b[3]) / 2


def panel(d, box, title, key, f):
    d.rounded_rectangle(box, 14, fill=FILL[key], outline=EDGE[key], width=3)
    d.text((box[0] + 14, box[1] + 8), title, fill=EDGE[key], font=f)


def node(d, box, text, f):
    d.rounded_rectangle(box, 10, fill=(255, 255, 255), outline=INK, width=2)
    cx, cy = C(box)
    lines = text.split("\n")
    y = cy - 7.5 * len(lines) + 1
    for line in lines:
        d.text((cx, y), line, fill=INK, font=f, anchor="mt")
        y += 15


def wire(d, pts, color=TEAL, width=5, dashed=False, arrow=True):
    """Orthogonal polyline. Inserts corners if needed. Optional terminal arrow."""
    if len(pts) < 2:
        return
    path = [pts[0]]
    for p in pts[1:]:
        x0, y0 = path[-1]
        x1, y1 = p
        if abs(x1 - x0) > 1 and abs(y1 - y0) > 1:
            path.append((x0, y1))
        path.append((x1, y1))

    def seg(a, b):
        x0, y0 = a
        x1, y1 = b
        if dashed:
            length = max(1.0, math.hypot(x1 - x0, y1 - y0))
            dash, gap = 10.0, 8.0
            dx, dy = x1 - x0, y1 - y0
            drawn = 0.0
            on = True
            while drawn < length:
                chunk = dash if on else gap
                t0 = drawn / length
                t1 = min((drawn + chunk) / length, 1.0)
                if on:
                    d.line(
                        (
                            x0 + dx * t0,
                            y0 + dy * t0,
                            x0 + dx * t1,
                            y0 + dy * t1,
                        ),
                        fill=color,
                        width=width,
                    )
                drawn += chunk
                on = not on
            # always cap the tip so the wire never looks severed
            d.line(
                (x0 + dx * 0.97, y0 + dy * 0.97, x1, y1),
                fill=color,
                width=width,
            )
        else:
            d.line([a, b], fill=color, width=width)

    for i in range(len(path) - 1):
        seg(path[i], path[i + 1])

    if not arrow:
        return
    x0, y0 = path[-2]
    x1, y1 = path[-1]
    ang = math.atan2(y1 - y0, x1 - x0)
    sz = 11
    d.polygon(
        [
            (x1, y1),
            (x1 - sz * math.cos(ang - 0.35), y1 - sz * math.sin(ang - 0.35)),
            (x1 - sz * math.cos(ang + 0.35), y1 - sz * math.sin(ang + 0.35)),
        ],
        fill=color,
    )


def label(d, xy, text, f, color=ACCENT):
    d.text(xy, text, fill=color, font=f)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    ft, fp, fn, fl, fs = font(28, True), font(16, True), font(13), font(12, True), font(12)

    d.text((W / 2, 16), "FSOC Virtual Tracker — PAT Architecture", fill=INK, font=ft, anchor="mt")
    d.text(
        (W / 2, 50),
        "teal = forward path   ·   orange = camera control   ·   wires only in gutters   ·   no message modem",
        fill=MUTED,
        font=fs,
        anchor="mt",
    )

    # Margins / dedicated lanes (never shared for different signals)
    SPINE = 36          # far-left orange + mode share this vertical outside panels
    G_HY = 845          # Hybrid → Kalman gutter lane
    G_LK = 885          # Link → Ready gutter lane (offset, no overlap)
    BUS = 2100          # control bus (margin from canvas edge)

    Y_UI = 188          # under UI
    Y_MODE = 498        # mode highway (UI → detectors)
    Y_FOV = 522         # FOV highway (noise → detectors), separate from mode
    Y_OUT = 1120        # between track and outputs
    Y_RET = 1580        # under outputs (orange return only)

    # Panels — leave gutters between them
    p_ui = (70, 68, 1980, 168)
    p_scene = (70, 210, 820, 470)
    p_chan = (920, 210, 1980, 470)
    p_det = (70, 540, 820, 1040)
    p_track = (920, 540, 1980, 1040)
    p_out = (70, 1160, 1980, 1500)

    panel(d, p_ui, "1. Operator / UI", "ui", fp)
    panel(d, p_scene, "2. Virtual World", "scene", fp)
    panel(d, p_chan, "3. Disturbances + Physics", "chan", fp)
    panel(d, p_det, "4. Detection", "det", fp)
    panel(d, p_track, "5. Tracking + Control", "track", fp)
    panel(d, p_out, "6. Outputs", "out", fp)

    d.line((BUS, 230, BUS, 1000), fill=ORANGE, width=6)
    label(d, (BUS - 8, 212), "control bus", fl, ORANGE)

    # Nodes
    n_ui = (180, 102, 1860, 148)

    n_be = (110, 255, 340, 310)
    n_cl = (400, 255, 650, 310)
    n_sr = (250, 340, 560, 390)
    n_cam = (230, 405, 580, 450)

    n_tu = (980, 255, 1300, 325)
    n_vi = (1360, 255, 1580, 325)
    n_no = (1640, 255, 1900, 325)
    n_lk = (1200, 360, 1620, 430)

    n_cls = (110, 600, 370, 690)
    n_ai = (430, 600, 680, 690)
    n_hy = (230, 780, 560, 890)

    n_kf = (980, 590, 1320, 700)
    n_re = (1480, 590, 1860, 700)
    n_rd = (980, 800, 1320, 900)
    n_fi = (1480, 800, 1860, 980)

    n_hud = (120, 1220, 560, 1420)
    n_csv = (680, 1220, 1180, 1420)
    n_rpt = (1300, 1220, 1860, 1420)

    for box, text in [
        (n_ui, "Control Panel   ·   sliders · presets · Classical/AI · beacons"),
        (n_be, "Moving Beacon(s)"),
        (n_cl, "Stars / Glints"),
        (n_sr, "Scene Render"),
        (n_cam, "Virtual Camera\nAZ/EL + FOV"),
        (n_tu, "Turbulence\nCn² → wander / scintillation"),
        (n_vi, "Platform Vibration"),
        (n_no, "Sensor Noise"),
        (n_lk, "Link Budget\nSNR / fade / pointing loss"),
        (n_cls, "Classical\nthreshold + centroid"),
        (n_ai, "YOLO AI"),
        (n_hy, "Hybrid Fusion"),
        (n_kf, "Kalman Tracker\nLOCKED / COASTING / LOST"),
        (n_re, "Spiral Re-acquisition"),
        (n_rd, "Link Readiness Score"),
        (n_fi, "Fine Pointing Mock\n4-QD + FSM"),
        (n_hud, "Live HUD µrad"),
        (n_csv, "CSV + Run Sheet"),
        (n_rpt, "Streamlit Report / PDF"),
    ]:
        node(d, box, text, fn)

    # ---- Scene internals ----
    wire(d, [B(n_be), (C(n_be)[0], 325), (C(n_sr)[0] - 50, 325), (C(n_sr)[0] - 50, n_sr[1])])
    wire(d, [B(n_cl), (C(n_cl)[0], 325), (C(n_sr)[0] + 50, 325), (C(n_sr)[0] + 50, n_sr[1])])
    wire(d, [B(n_sr), T(n_cam)])

    # ---- UI → targets (drop in Y_UI gutter, never through panels) ----
    wire(d, [(C(n_be)[0], n_ui[3]), (C(n_be)[0], Y_UI), T(n_be)])
    label(d, (C(n_be)[0] + 12, Y_UI - 18), "config", fl)

    wire(d, [(C(n_tu)[0], n_ui[3]), (C(n_tu)[0], Y_UI), T(n_tu)])
    wire(d, [(C(n_vi)[0], n_ui[3]), (C(n_vi)[0], Y_UI), T(n_vi)])
    wire(d, [(C(n_no)[0], n_ui[3]), (C(n_no)[0], Y_UI), T(n_no)])

    # mode: left edge of UI → spine → Y_MODE → both detectors
    wire(
        d,
        [(n_ui[0], n_ui[3]), (n_ui[0], Y_UI), (SPINE, Y_UI), (SPINE, Y_MODE), (C(n_cls)[0], Y_MODE), T(n_cls)],
    )
    wire(d, [(C(n_cls)[0], Y_MODE), (C(n_ai)[0], Y_MODE), T(n_ai)], arrow=True)
    label(d, (70, Y_MODE - 18), "mode", fl)

    # ---- Camera → channel via dual gutters ----
    wire(d, [R(n_cam), (G_HY, C(n_cam)[1]), (G_HY, C(n_tu)[1]), L(n_tu)])
    wire(d, [R(n_tu), L(n_vi)])
    wire(d, [R(n_vi), L(n_no)])
    wire(d, [R(n_cam), (G_LK, C(n_cam)[1] + 28), (G_LK, C(n_lk)[1]), L(n_lk)])

    # ---- FOV: noise → dedicated Y_FOV → Classical top (full path, no stub) ----
    wire(
        d,
        [B(n_no), (C(n_no)[0], Y_FOV), (C(n_cls)[0], Y_FOV), (C(n_cls)[0], n_cls[1] - 2)],
    )
    label(d, (1500, Y_FOV + 4), "FOV", fl)

    # ---- Detection fusion → Kalman via G_HY ----
    wire(d, [B(n_cls), (C(n_cls)[0], 730), (C(n_hy)[0] - 60, 730), (C(n_hy)[0] - 60, n_hy[1])])
    wire(d, [B(n_ai), (C(n_ai)[0], 730), (C(n_hy)[0] + 60, 730), (C(n_hy)[0] + 60, n_hy[1])])
    wire(d, [R(n_hy), (G_HY, C(n_hy)[1]), (G_HY, C(n_kf)[1]), L(n_kf)])

    # ---- Tracking local ----
    wire(d, [R(n_kf), L(n_re)], dashed=True)
    label(d, (1360, 625), "LOST", fl)
    wire(d, [B(n_kf), T(n_rd)])

    # Link → Ready via G_LK only (never through Kalman or Fine).
    y_link = 535  # mid gutter (470..540)
    wire(
        d,
        [
            B(n_lk),
            (C(n_lk)[0], y_link),
            (G_LK, y_link),
            (G_LK, C(n_rd)[1]),
            L(n_rd),
        ],
    )

    wire(d, [R(n_rd), L(n_fi)])
    label(d, (1365, 835), "handoff", fl)

    # ---- Outputs: left lane in column gutter ----
    OUT_L = 870
    wire(d, [L(n_kf), (OUT_L, C(n_kf)[1]), (OUT_L, Y_OUT), (C(n_hud)[0], Y_OUT), T(n_hud)])
    wire(
        d,
        [
            B(n_rd),
            (C(n_rd)[0], n_rd[3] + 36),
            (OUT_L + 40, n_rd[3] + 36),
            (OUT_L + 40, Y_OUT),
            (C(n_hud)[0] + 70, Y_OUT),
            (C(n_hud)[0] + 70, n_hud[1]),
        ],
    )
    GAP = 1400
    wire(d, [(n_kf[2], n_kf[3]), (GAP, n_kf[3]), (GAP, Y_OUT), (C(n_csv)[0], Y_OUT), T(n_csv)])
    wire(d, [R(n_csv), L(n_rpt)])

    # ---- Orange control: drive in mid gutter ABOVE track (below FOV/mode) ----
    drive_y = 478
    up_x = n_kf[2] + 36
    wire(
        d,
        [(n_kf[2], C(n_kf)[1]), (up_x, C(n_kf)[1]), (up_x, drive_y), (BUS, drive_y)],
        color=ORANGE,
        width=6,
    )
    label(d, (BUS - 10, drive_y - 18), "drive", fl, ORANGE)
    # solid tip so dashed re-acq meets the bus cleanly
    wire(d, [R(n_re), (BUS, C(n_re)[1])], color=ORANGE, width=6, dashed=True, arrow=False)
    wire(d, [R(n_fi), (BUS, C(n_fi)[1])], color=ORANGE, width=6)

    # Return ONLY under outputs (Y_RET), never across output drops
    wire(
        d,
        [(BUS, C(n_fi)[1]), (BUS, Y_RET), (SPINE, Y_RET), (SPINE, C(n_cam)[1]), L(n_cam)],
        color=ORANGE,
        width=6,
    )
    label(d, (W / 2, Y_RET + 28), "aim → camera (drive · re-acq · fine)", fl, ORANGE)

    d.text(
        (W / 2, 1685),
        "Classical + YOLO both feed Hybrid   ·   Link Budget is parallel to turb→vib→noise   ·   Readiness gates Fine handoff",
        fill=MUTED,
        font=fs,
        anchor="mt",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG")
    (ROOT / "docs" / "architecture_layout.png").write_bytes(OUT.read_bytes())
    print(f"Wrote {OUT}  size={OUT.stat().st_size}")


if __name__ == "__main__":
    main()
