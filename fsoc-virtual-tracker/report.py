"""Streamlit performance report for FSOC Virtual Tracker run logs."""

from __future__ import annotations

import json
from dataclasses import dataclass
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from metrics.csv_schema import CSV_COLUMNS, LEGACY_REQUIRED_COLUMNS, OPTIONAL_COLUMNS

LOGS_DIR = ROOT / "logs"
STATE_COLORS = {
    "LOCKED": "#48dc78",
    "COASTING": "#f0c840",
    "LOST": "#eb5048",
}
STAGE_COLORS = {
    "COARSE": "#5ab4ff",
    "FINE": "#c084fc",
}
TRACKING_STATES = ("LOCKED", "COASTING", "LOST")


@dataclass(frozen=True)
class RunSummary:
    label: str
    avg_fps: float
    avg_pixel_error: float
    avg_link_readiness: float
    total_reacquisitions: int
    pct_locked: float
    pct_coasting: float
    pct_lost: float
    active_detector: str
    row_count: int
    duration_seconds: float
    avg_angular_error_urad: float = 0.0
    handoff_count: int = 0


def list_log_files() -> list[Path]:
    if not LOGS_DIR.is_dir():
        return []
    files = sorted(LOGS_DIR.glob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    return files


def load_run_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [column for column in LEGACY_REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in {path.name}: {', '.join(missing)}")

    for column in OPTIONAL_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan if column != "pat_stage" else "COARSE"

    use_cols = [c for c in CSV_COLUMNS if c in df.columns]
    df = df[use_cols].copy()
    numeric_columns = [
        "fps",
        "pixel_error",
        "angular_error_urad",
        "boresight_urad",
        "az_urad",
        "el_urad",
        "handoff_count",
        "turbulence_strength",
        "vibration_amplitude",
        "sensor_noise_level",
        "link_readiness_score",
        "cumulative_lost_seconds",
        "reacquisition_count",
    ]
    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["tracking_state"] = df["tracking_state"].astype(str).str.upper()
    df["active_detector"] = df["active_detector"].astype(str).str.lower()
    if "pat_stage" in df.columns:
        df["pat_stage"] = df["pat_stage"].astype(str).str.upper().fillna("COARSE")
    df = df.dropna(subset=["timestamp", "fps", "pixel_error", "link_readiness_score"])
    df = df.reset_index(drop=True)

    if df.empty:
        raise ValueError(f"No usable rows in {path.name}")

    start_time = df["timestamp"].iloc[0]
    df["elapsed_s"] = (df["timestamp"] - start_time).dt.total_seconds()
    if df["elapsed_s"].nunique() <= 1:
        df["elapsed_s"] = df.index.astype(float)
    return df


def summarize_run(df: pd.DataFrame, label: str) -> RunSummary:
    state_counts = df["tracking_state"].value_counts()
    total_rows = len(df)
    duration = float(df["elapsed_s"].iloc[-1] - df["elapsed_s"].iloc[0])
    if duration <= 0.0:
        duration = float(total_rows)

    detectors = df["active_detector"].dropna().unique().tolist()
    if len(detectors) == 1:
        active_detector = detectors[0]
    elif len(detectors) == 0:
        active_detector = "unknown"
    else:
        active_detector = ", ".join(sorted(detectors))

    avg_urad = (
        float(df["angular_error_urad"].mean())
        if "angular_error_urad" in df.columns and df["angular_error_urad"].notna().any()
        else 0.0
    )
    handoffs = (
        int(df["handoff_count"].max())
        if "handoff_count" in df.columns and df["handoff_count"].notna().any()
        else 0
    )

    return RunSummary(
        label=label,
        avg_fps=float(df["fps"].mean()),
        avg_pixel_error=float(df["pixel_error"].mean()),
        avg_link_readiness=float(df["link_readiness_score"].mean()),
        total_reacquisitions=int(df["reacquisition_count"].max()),
        pct_locked=100.0 * state_counts.get("LOCKED", 0) / total_rows,
        pct_coasting=100.0 * state_counts.get("COASTING", 0) / total_rows,
        pct_lost=100.0 * state_counts.get("LOST", 0) / total_rows,
        active_detector=active_detector,
        row_count=total_rows,
        duration_seconds=duration,
        avg_angular_error_urad=avg_urad,
        handoff_count=handoffs,
    )


def load_session_summary(csv_path: Path) -> dict | None:
    summary_path = csv_path.with_suffix(".summary.json")
    if not summary_path.is_file():
        return None
    return json.loads(summary_path.read_text(encoding="utf-8"))


def render_session_summary(summary: dict) -> None:
    st.markdown("**SIH session metrics** (from `.summary.json`)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Max pixel error", f"{summary.get('max_pixel_error_px', 0):.2f} px")
    c2.metric("Lock retention", f"{summary.get('lock_retention_pct', 0):.1f}%")
    c3.metric("Avg acquisition", f"{summary.get('avg_acquisition_time_s', 0):.2f} s")
    c4.metric("Avg detect time", f"{summary.get('avg_processing_time_ms', 0):.2f} ms")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("RMS angular error", f"{summary.get('rms_angular_error_urad', 0):.0f} µrad")
    c6.metric("Fine duty cycle", f"{summary.get('pct_fine', 0):.1f}%")
    c7.metric("Handoffs", f"{summary.get('handoff_count', 0)}")
    c8.metric("Detect p95", f"{summary.get('p95_processing_time_ms', 0):.1f} ms")


def render_summary_cards(summary: RunSummary, session: dict | None = None) -> None:
    st.markdown(f"**{summary.label}**")
    row1 = st.columns(4)
    row1[0].metric("Avg FPS", f"{summary.avg_fps:.1f}")
    row1[1].metric("Avg Pixel Error", f"{summary.avg_pixel_error:.2f} px")
    row1[2].metric("Avg Angular Error", f"{summary.avg_angular_error_urad:.0f} µrad")
    row1[3].metric("Avg Link Readiness", f"{summary.avg_link_readiness:.3f}")

    row2 = st.columns(5)
    row2[0].metric("LOCKED", f"{summary.pct_locked:.1f}%")
    row2[1].metric("COASTING", f"{summary.pct_coasting:.1f}%")
    row2[2].metric("LOST", f"{summary.pct_lost:.1f}%")
    row2[3].metric("Re-acquisitions", f"{summary.total_reacquisitions}")
    row2[4].metric("Fine handoffs", f"{summary.handoff_count}")
    if session:
        render_session_summary(session)


def plot_tracking_state_strip(ax: plt.Axes, df: pd.DataFrame, title: str) -> None:
    times = df["elapsed_s"].to_numpy()
    if len(times) == 0:
        return

    segment_starts = times
    segment_ends = list(times[1:]) + [times[-1] + 1.0]
    for start, end, state in zip(segment_starts, segment_ends, df["tracking_state"]):
        color = STATE_COLORS.get(state, "#888888")
        ax.broken_barh([(start, max(end - start, 0.5))], (0.2, 0.6), facecolors=color)

    ax.set_yticks([])
    ax.set_xlim(float(times[0]), float(segment_ends[-1]))
    ax.set_ylim(0.0, 1.0)
    ax.set_title(title)
    ax.set_xlabel("Elapsed time (s)")
    ax.grid(axis="x", alpha=0.2)


def plot_run_charts(df: pd.DataFrame, title_prefix: str = "") -> None:
    prefix = f"{title_prefix} — " if title_prefix else ""

    if "angular_error_urad" in df.columns and df["angular_error_urad"].notna().any():
        fig_ang, ax_ang = plt.subplots(figsize=(10, 3))
        ax_ang.plot(df["elapsed_s"], df["angular_error_urad"], color="#5ab4ff", linewidth=1.5)
        ax_ang.set_title(f"{prefix}Angular Tracking Error (primary KPI)")
        ax_ang.set_xlabel("Elapsed time (s)")
        ax_ang.set_ylabel("Error (µrad)")
        ax_ang.grid(alpha=0.25)
        st.pyplot(fig_ang)
        plt.close(fig_ang)

    fig_error, ax_error = plt.subplots(figsize=(10, 3))
    ax_error.plot(df["elapsed_s"], df["pixel_error"], color="#5ab4ff", linewidth=1.5)
    ax_error.set_title(f"{prefix}Pixel Tracking Error")
    ax_error.set_xlabel("Elapsed time (s)")
    ax_error.set_ylabel("Error (px)")
    ax_error.grid(alpha=0.25)
    st.pyplot(fig_error)
    plt.close(fig_error)

    fig_ready, ax_ready = plt.subplots(figsize=(10, 3))
    ax_ready.plot(df["elapsed_s"], df["link_readiness_score"], color="#48dc78", linewidth=1.5)
    ax_ready.axhline(0.7, color="#48dc78", linestyle="--", linewidth=0.8, alpha=0.5, label="handoff enter")
    ax_ready.axhline(0.55, color="#f0c840", linestyle="--", linewidth=0.8, alpha=0.5, label="handoff exit")
    ax_ready.axhline(0.3, color="#eb5048", linestyle="--", linewidth=0.8, alpha=0.5)
    ax_ready.set_ylim(0.0, 1.05)
    ax_ready.set_title(f"{prefix}Link Readiness + Handoff Gates")
    ax_ready.set_xlabel("Elapsed time (s)")
    ax_ready.set_ylabel("Score")
    ax_ready.legend(loc="upper right", fontsize=8)
    ax_ready.grid(alpha=0.25)
    st.pyplot(fig_ready)
    plt.close(fig_ready)

    if "pat_stage" in df.columns:
        fig_stage, ax_stage = plt.subplots(figsize=(10, 1.2))
        times = df["elapsed_s"].to_numpy()
        segment_ends = list(times[1:]) + [times[-1] + 1.0]
        for start, end, stage in zip(times, segment_ends, df["pat_stage"]):
            color = STAGE_COLORS.get(str(stage).upper(), "#888888")
            ax_stage.broken_barh([(start, max(end - start, 0.5))], (0.2, 0.6), facecolors=color)
        ax_stage.set_yticks([])
        ax_stage.set_xlim(float(times[0]), float(segment_ends[-1]))
        ax_stage.set_ylim(0.0, 1.0)
        ax_stage.set_title(f"{prefix}PAT Stage (COARSE / FINE handoff)")
        ax_stage.set_xlabel("Elapsed time (s)")
        legend_handles = [
            plt.Line2D([0], [0], color=STAGE_COLORS[s], lw=8, label=s)
            for s in ("COARSE", "FINE")
        ]
        ax_stage.legend(handles=legend_handles, loc="upper center", ncol=2, frameon=False)
        st.pyplot(fig_stage)
        plt.close(fig_stage)

    fig_state, ax_state = plt.subplots(figsize=(10, 1.2))
    plot_tracking_state_strip(ax_state, df, f"{prefix}Tracking State")
    legend_handles = [
        plt.Line2D([0], [0], color=STATE_COLORS[state], lw=8, label=state)
        for state in TRACKING_STATES
    ]
    ax_state.legend(handles=legend_handles, loc="upper center", ncol=3, frameon=False)
    st.pyplot(fig_state)
    plt.close(fig_state)


def plot_comparison_overlay(runs: list[tuple[str, pd.DataFrame]], column: str, title: str, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 3))
    palette = ["#5ab4ff", "#ff8c5a", "#c084fc"]
    for index, (label, df) in enumerate(runs):
        ax.plot(
            df["elapsed_s"],
            df[column],
            label=label,
            linewidth=1.5,
            color=palette[index % len(palette)],
        )
    ax.set_title(title)
    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    ax.legend()
    st.pyplot(fig)
    plt.close(fig)


def build_report_text(summary: RunSummary, session: dict | None) -> str:
    lines = [
        "FSOC Virtual Tracker — Performance Report",
        "=" * 44,
        f"Run: {summary.label}",
        f"Duration: {summary.duration_seconds:.0f} s",
        f"Detector: {summary.active_detector}",
        f"Avg FPS: {summary.avg_fps:.1f}",
        f"Avg pixel error: {summary.avg_pixel_error:.2f} px",
        f"Avg angular error: {summary.avg_angular_error_urad:.0f} µrad",
        f"Avg link readiness: {summary.avg_link_readiness:.3f}",
        f"LOCKED: {summary.pct_locked:.1f}%  COASTING: {summary.pct_coasting:.1f}%  LOST: {summary.pct_lost:.1f}%",
        f"Re-acquisitions: {summary.total_reacquisitions}",
        f"Fine handoffs: {summary.handoff_count}",
    ]
    if session:
        lines.extend(
            [
                "",
                "SIH session metrics:",
                f"  Max pixel error: {session.get('max_pixel_error_px', 0):.2f} px",
                f"  Lock retention: {session.get('lock_retention_pct', 0):.1f}%",
                f"  Avg acquisition time: {session.get('avg_acquisition_time_s', 0):.3f} s",
                f"  Avg processing time: {session.get('avg_processing_time_ms', 0):.2f} ms",
                f"  RMS angular error: {session.get('rms_angular_error_urad', 0):.0f} µrad",
                f"  Fine duty cycle: {session.get('pct_fine', 0):.1f}%",
            ]
        )
    return "\n".join(lines)


def build_report_pdf_bytes(
    summary: RunSummary,
    session: dict | None,
    df: pd.DataFrame,
) -> bytes:
    """Judge-facing multi-page PDF (summary + KPI charts)."""
    from io import BytesIO

    from matplotlib.backends.backend_pdf import PdfPages

    buffer = BytesIO()
    with PdfPages(buffer) as pdf:
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")
        ax.set_title("FSOC Virtual Tracker — Performance Report", fontsize=14, pad=12)
        ax.text(
            0.05,
            0.92,
            build_report_text(summary, session),
            transform=ax.transAxes,
            va="top",
            ha="left",
            family="monospace",
            fontsize=9,
        )
        pdf.savefig(fig)
        plt.close(fig)

        if "angular_error_urad" in df.columns and df["angular_error_urad"].notna().any():
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df["elapsed_s"], df["angular_error_urad"], color="#5ab4ff", linewidth=1.4)
            ax.set_title("Angular Tracking Error")
            ax.set_xlabel("Elapsed time (s)")
            ax.set_ylabel("Error (µrad)")
            ax.grid(alpha=0.25)
            pdf.savefig(fig)
            plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(df["elapsed_s"], df["pixel_error"], color="#5ab4ff", linewidth=1.4)
        ax.set_title("Pixel Tracking Error")
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Error (px)")
        ax.grid(alpha=0.25)
        pdf.savefig(fig)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(df["elapsed_s"], df["link_readiness_score"], color="#48dc78", linewidth=1.4)
        ax.axhline(0.7, color="#48dc78", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.axhline(0.55, color="#f0c840", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.set_ylim(0.0, 1.05)
        ax.set_title("Link Readiness")
        ax.set_xlabel("Elapsed time (s)")
        ax.set_ylabel("Score")
        ax.grid(alpha=0.25)
        pdf.savefig(fig)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 2.2))
        plot_tracking_state_strip(ax, df, "Tracking State")
        pdf.savefig(fig)
        plt.close(fig)

    return buffer.getvalue()


def file_label(path: Path) -> str:
    return path.name


def main() -> None:
    st.set_page_config(page_title="FSOC Run Report", layout="wide")
    st.title("FSOC Virtual Tracker — Run Report")
    st.caption("Load performance CSV logs from `logs/` and compare classical vs AI detector runs.")

    log_files = list_log_files()
    if not log_files:
        st.error(f"No CSV files found in `{LOGS_DIR}`. Run the simulator first to generate logs.")
        st.stop()

    default_a = log_files[0]
    default_b = log_files[1] if len(log_files) > 1 else log_files[0]
    file_options = {file_label(path): path for path in log_files}

    with st.sidebar:
        st.header("Data")
        compare_mode = st.toggle("Compare two runs", value=len(log_files) > 1)
        run_a_name = st.selectbox(
            "Run A",
            options=list(file_options.keys()),
            index=list(file_options.keys()).index(file_label(default_a)),
        )
        run_b_name = None
        if compare_mode:
            run_b_name = st.selectbox(
                "Run B",
                options=list(file_options.keys()),
                index=list(file_options.keys()).index(file_label(default_b)),
            )
        st.markdown("---")
        st.markdown("**State colors**")
        st.markdown(
            ":green[LOCKED] · :orange[COASTING] · :red[LOST]"
        )

    run_a_path = file_options[run_a_name]
    try:
        run_a_df = load_run_csv(run_a_path)
        summary_a = summarize_run(run_a_df, run_a_name)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if compare_mode and run_b_name is not None:
        run_b_path = file_options[run_b_name]
        if run_b_path == run_a_path:
            st.warning("Run A and Run B are the same file. Pick two different logs for a meaningful comparison.")
        try:
            run_b_df = load_run_csv(run_b_path)
            summary_b = summarize_run(run_b_df, run_b_name)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        st.subheader("Summary Comparison")
        col_a, col_b = st.columns(2)
        with col_a:
            render_summary_cards(summary_a, load_session_summary(run_a_path))
        with col_b:
            render_summary_cards(summary_b, load_session_summary(run_b_path))

        st.subheader("Overlay Charts")
        plot_comparison_overlay(
            [(summary_a.label, run_a_df), (summary_b.label, run_b_df)],
            "pixel_error",
            "Pixel Tracking Error (comparison)",
            "Error (px)",
        )
        plot_comparison_overlay(
            [(summary_a.label, run_a_df), (summary_b.label, run_b_df)],
            "link_readiness_score",
            "Link Readiness Score (comparison)",
            "Score",
        )

        st.subheader("Per-Run Detail")
        detail_a, detail_b = st.columns(2)
        with detail_a:
            plot_run_charts(run_a_df, title_prefix=summary_a.label)
        with detail_b:
            plot_run_charts(run_b_df, title_prefix=summary_b.label)
    else:
        st.subheader("Summary")
        session_a = load_session_summary(run_a_path)
        render_summary_cards(summary_a, session_a)
        st.download_button(
            "Download report (.txt)",
            data=build_report_text(summary_a, session_a),
            file_name=f"{run_a_path.stem}_report.txt",
            mime="text/plain",
        )
        st.download_button(
            "Download report (.pdf)",
            data=build_report_pdf_bytes(summary_a, session_a, run_a_df),
            file_name=f"{run_a_path.stem}_report.pdf",
            mime="application/pdf",
        )
        st.subheader("Timeline")
        plot_run_charts(run_a_df)


if __name__ == "__main__":
    main()
