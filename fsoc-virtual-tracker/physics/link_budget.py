"""Simplified optical link budget for coarse-PAT handoff scoring.

P_rx model follows the standard directed FSO form used in LEO/terrestrial
budgets (see e.g. IISc/QOSMIC probabilistic optical link budget, arXiv:2507.20908):

  P_rx = P_tx · η_tx · η_rx · G_geo · T_atm · L_pe · I_scint

This is a decision-support SNR, not a certified BER / outage calculator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkParams:
    wavelength_m: float = 976e-9
    tx_power_w: float = 0.5
    tx_efficiency: float = 0.7
    rx_efficiency: float = 0.7
    rx_aperture_m: float = 0.08
    # Acquisition beacon half-angle divergence (rad). ~0.3° full ≈ 2.6 mrad half.
    divergence_half_rad: float = 2.6e-3
    path_length_m: float = 8_000.0
    # Clear-air static transmittance (Beer–Lambert stand-in).
    atm_transmittance: float = 0.75
    # Equivalent noise power for coarse sensor SNR (W). Tuned for demo dynamic range.
    noise_equivalent_power_w: float = 5.0e-9


@dataclass(frozen=True)
class LinkBudgetResult:
    p_rx_w: float
    snr_db: float
    pointing_loss: float
    geometric_collection: float
    fade_margin_db: float


class OpticalLink:
    """Compute received power and SNR from pointing residual + channel state."""

    def __init__(self, params: LinkParams | None = None) -> None:
        self.params = params or LinkParams()

    def geometric_collection(self) -> float:
        """Fraction of Tx beam captured by Rx aperture at range L."""
        p = self.params
        spot_radius = max(p.divergence_half_rad * p.path_length_m, 1e-6)
        area_spot = math.pi * spot_radius * spot_radius
        area_rx = math.pi * (0.5 * p.rx_aperture_m) ** 2
        return float(min(1.0, area_rx / area_spot))

    def pointing_loss(self, residual_urad: float) -> float:
        """Gaussian beam pointing loss ≈ exp(-2 (θ/θ_div)²)."""
        p = self.params
        theta_rad = abs(residual_urad) * 1e-6
        ratio = theta_rad / max(p.divergence_half_rad, 1e-9)
        return float(math.exp(-2.0 * ratio * ratio))

    def compute(
        self,
        residual_urad: float,
        scintillation: float = 1.0,
        atm_dynamic: float = 1.0,
    ) -> LinkBudgetResult:
        p = self.params
        g_geo = self.geometric_collection()
        l_pe = self.pointing_loss(residual_urad)
        i_scint = max(0.02, float(scintillation))
        t_dyn = max(0.05, min(1.0, float(atm_dynamic)))

        p_rx = (
            p.tx_power_w
            * p.tx_efficiency
            * p.rx_efficiency
            * g_geo
            * p.atm_transmittance
            * t_dyn
            * l_pe
            * i_scint
        )
        snr_linear = p_rx / max(p.noise_equivalent_power_w, 1e-30)
        snr_db = 10.0 * math.log10(max(snr_linear, 1e-30))
        # Fade margin vs a 10 dB handoff floor.
        fade_margin_db = snr_db - 10.0
        return LinkBudgetResult(
            p_rx_w=p_rx,
            snr_db=snr_db,
            pointing_loss=l_pe,
            geometric_collection=g_geo,
            fade_margin_db=fade_margin_db,
        )

    def spot_sigma_px(
        self,
        ifov_urad: float,
        base_sigma_px: float = 2.5,
    ) -> float:
        """Apparent beacon sigma in pixels from divergence vs IFOV (clamped)."""
        # Project half-angle to pixels at the virtual focal plane representation.
        angular_sigma_urad = self.params.divergence_half_rad * 1e6 * 0.15
        from_optics = angular_sigma_urad / max(ifov_urad, 1e-6)
        return float(max(base_sigma_px, min(from_optics, 12.0)))
