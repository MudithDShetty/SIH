"""Control package: re-acquisition search and coarse-to-fine handoff.

Modules
-------
reacquisition
    Covariance-scaled raster (default) / spiral waypoint search when LOST.
fine_pointing
    Readiness-gated mock 4-QD + FSM fine stage.
"""

from control.fine_pointing import (
    CAPTURE_RADIUS_URAD,
    HANDOFF_CRITERIA,
    HANDOFF_ENTER,
    HANDOFF_EXIT,
    HANDOFF_STABLE_FRAMES,
    STAGE_COARSE,
    STAGE_FINE,
    FinePointingController,
    FinePointingState,
)
from control.reacquisition import ReacquisitionController

__all__ = [
    "CAPTURE_RADIUS_URAD",
    "HANDOFF_CRITERIA",
    "HANDOFF_ENTER",
    "HANDOFF_EXIT",
    "HANDOFF_STABLE_FRAMES",
    "STAGE_COARSE",
    "STAGE_FINE",
    "FinePointingController",
    "FinePointingState",
    "ReacquisitionController",
]
