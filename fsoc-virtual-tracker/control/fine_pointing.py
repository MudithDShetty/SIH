"""Fine-pointing stage: mock 4-quadrant detector + FSM tip/tilt loop.

Handoff from coarse PAT when Link Readiness exceeds the enter threshold and the
beacon is inside the fine capture cone. Drops back to coarse on hysteresis exit,
LOST/COASTING, or when residual exceeds the capture cone.

Optional quad-channel noise and FSM command latency model demo realism without
claiming a calibrated flight plant.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

from tracker.kalman_tracker import TRACKING_COASTING, TRACKING_LOCKED, TRACKING_LOST

STAGE_COARSE = "COARSE"
STAGE_FINE = "FINE"

# Handoff thresholds (Link Readiness score).
HANDOFF_ENTER = 0.70
HANDOFF_EXIT = 0.55

# Capture cone for fine stage (µrad). ~600 µrad @ 6.25 µrad/px ≈ 96 px.
CAPTURE_RADIUS_URAD = 600.0
CAPTURE_DROP_URAD = 900.0

# Require N consecutive frames meeting enter criteria before handoff.
HANDOFF_STABLE_FRAMES = 12  # ~0.2 s @ 60 fps

# Fine FSM bandwidth (much faster than coarse gimbal slew).
FINE_SLEW_URAD_S = 4_000.0
QUAD_GAIN = 1.15  # soft saturation scale vs spot sigma

# Demo plant non-idealities (defaults mild).
DEFAULT_QUAD_NOISE_STD = 0.025
DEFAULT_FSM_LATENCY_S = 0.005  # 5 ms

# Documented operational handoff criteria (for reports / run sheets).
HANDOFF_CRITERIA = {
    "tracking_state": TRACKING_LOCKED,
    "readiness_enter": HANDOFF_ENTER,
    "readiness_exit": HANDOFF_EXIT,
    "residual_enter_urad": CAPTURE_RADIUS_URAD,
    "residual_drop_urad": CAPTURE_DROP_URAD,
    "stable_frames": HANDOFF_STABLE_FRAMES,
    "fade_margin_floor_db": 10.0,
    "quad_noise_std": DEFAULT_QUAD_NOISE_STD,
    "fsm_latency_s": DEFAULT_FSM_LATENCY_S,
}


@dataclass(frozen=True)
class FinePointingState:
    stage: str
    active: bool
    quad_x: float
    quad_y: float
    residual_urad: float
    handoff_count: int
    time_in_fine_s: float
    stable_frames: int = 0
    criteria_met: bool = False


class FinePointingController:
    """4-QD residual estimator + high-bandwidth tip/tilt nulling loop."""

    def __init__(
        self,
        handoff_enter: float = HANDOFF_ENTER,
        handoff_exit: float = HANDOFF_EXIT,
        capture_radius_urad: float = CAPTURE_RADIUS_URAD,
        fine_slew_urad_s: float = FINE_SLEW_URAD_S,
        stable_frames_required: int = HANDOFF_STABLE_FRAMES,
        quad_noise_std: float = DEFAULT_QUAD_NOISE_STD,
        fsm_latency_s: float = DEFAULT_FSM_LATENCY_S,
        seed: int | None = None,
    ) -> None:
        self.handoff_enter = handoff_enter
        self.handoff_exit = handoff_exit
        self.capture_radius_urad = capture_radius_urad
        self.fine_slew_urad_s = fine_slew_urad_s
        self.stable_frames_required = stable_frames_required
        self.quad_noise_std = max(0.0, float(quad_noise_std))
        self.fsm_latency_s = max(0.0, float(fsm_latency_s))
        self._rng = random.Random(seed)

        self.active = False
        self.handoff_count = 0
        self.time_in_fine_s = 0.0
        self.quad_x = 0.0
        self.quad_y = 0.0
        self.residual_urad = 0.0
        self._stable_frames = 0
        # Delayed (dx_px, dy_px) commands for FSM latency.
        self._command_queue: deque[tuple[float, float, float]] = deque()

    def reset(self) -> None:
        self.active = False
        self.quad_x = 0.0
        self.quad_y = 0.0
        self.residual_urad = 0.0
        self._stable_frames = 0
        self._command_queue.clear()

    def measure_quad(
        self,
        spot_local_x: float,
        spot_local_y: float,
        fov_width: float,
        fov_height: float,
        ifov_urad: float,
        spot_sigma_px: float,
    ) -> tuple[float, float, float]:
        """Return (quad_x, quad_y, residual_urad) from spot vs FOV center."""
        cx = fov_width * 0.5
        cy = fov_height * 0.5
        dx = spot_local_x - cx
        dy = spot_local_y - cy
        residual_urad = math.hypot(dx, dy) * ifov_urad
        denom = max(spot_sigma_px * QUAD_GAIN, 1.0)
        quad_x = max(-1.0, min(1.0, dx / denom))
        quad_y = max(-1.0, min(1.0, dy / denom))
        if self.quad_noise_std > 0.0:
            quad_x = max(
                -1.0,
                min(1.0, quad_x + self._rng.gauss(0.0, self.quad_noise_std)),
            )
            quad_y = max(
                -1.0,
                min(1.0, quad_y + self._rng.gauss(0.0, self.quad_noise_std)),
            )
            # Recompute residual direction magnitude from noisy quads (approx).
            residual_urad = math.hypot(quad_x, quad_y) * denom * ifov_urad
        return quad_x, quad_y, residual_urad

    def update(
        self,
        dt: float,
        *,
        readiness_score: float,
        tracking_state: str,
        spot_local: tuple[float, float] | None,
        fov_width: float,
        fov_height: float,
        ifov_urad: float,
        spot_sigma_px: float,
        camera,
    ) -> FinePointingState:
        """Update stage machine and optionally slew camera to null 4-QD residual."""
        if spot_local is not None:
            self.quad_x, self.quad_y, self.residual_urad = self.measure_quad(
                spot_local[0],
                spot_local[1],
                fov_width,
                fov_height,
                ifov_urad,
                spot_sigma_px,
            )
        else:
            self.quad_x = 0.0
            self.quad_y = 0.0
            self.residual_urad = float("inf")

        criteria_met = (
            tracking_state == TRACKING_LOCKED
            and readiness_score >= self.handoff_enter
            and spot_local is not None
            and self.residual_urad <= self.capture_radius_urad
        )
        if criteria_met:
            self._stable_frames += 1
        else:
            self._stable_frames = 0

        can_enter = criteria_met and self._stable_frames >= self.stable_frames_required
        must_exit = (
            tracking_state in (TRACKING_LOST, TRACKING_COASTING)
            or readiness_score < self.handoff_exit
            or spot_local is None
            or self.residual_urad > CAPTURE_DROP_URAD
        )

        if self.active:
            if must_exit:
                self.active = False
                self._stable_frames = 0
                self._command_queue.clear()
            else:
                self.time_in_fine_s += dt
                self._queue_fsm_correction(dt, ifov_urad)
                self._flush_due_commands(dt, camera)
        elif can_enter:
            self.active = True
            self.handoff_count += 1
            self.time_in_fine_s = 0.0
            self._queue_fsm_correction(dt, ifov_urad)
            self._flush_due_commands(dt, camera)
        else:
            self._command_queue.clear()

        return FinePointingState(
            stage=STAGE_FINE if self.active else STAGE_COARSE,
            active=self.active,
            quad_x=self.quad_x,
            quad_y=self.quad_y,
            residual_urad=(
                self.residual_urad if math.isfinite(self.residual_urad) else 0.0
            ),
            handoff_count=self.handoff_count,
            time_in_fine_s=self.time_in_fine_s,
            stable_frames=self._stable_frames,
            criteria_met=criteria_met,
        )

    def _queue_fsm_correction(self, dt: float, ifov_urad: float) -> None:
        if self.residual_urad <= 1e-6 or ifov_urad <= 1e-12:
            return
        mag = math.hypot(self.quad_x, self.quad_y)
        if mag <= 1e-9:
            return
        ux = self.quad_x / mag
        uy = self.quad_y / mag
        max_step_urad = self.fine_slew_urad_s * dt
        step_urad = min(self.residual_urad, max_step_urad)
        step_px = step_urad / ifov_urad
        due_in = self.fsm_latency_s
        self._command_queue.append((due_in, ux * step_px, uy * step_px))

    def _flush_due_commands(self, dt: float, camera) -> None:
        remaining: deque[tuple[float, float, float]] = deque()
        while self._command_queue:
            due_in, dx, dy = self._command_queue.popleft()
            due_in -= dt
            if due_in <= 0.0:
                camera.x += dx
                camera.y += dy
            else:
                remaining.append((due_in, dx, dy))
        self._command_queue = remaining
