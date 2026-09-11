"""Statistical atmospheric channel for real-time FSOC PAT simulation.

Implements Andrews-style order-of-magnitude models suitable for a 60 fps
coarse-PAT loop. This is NOT a split-step / phase-screen propagator.

References (formulas adapted for horizontal / UAV-class paths):
  - Andrews & Phillips, Laser Beam Propagation through Random Media
  - Rytov variance → scintillation; Fried r0; angle-of-arrival / beam wander
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

# Slider strength 0..10 maps onto this Cn² span (m^-2/3).
# Calm ~1e-17, moderate ~1e-14, strong ~1e-12 (horizontal-path order of magnitude).
CN2_MIN = 1.0e-17
CN2_MAX = 1.0e-12

# Default optical / geometric assumptions for the virtual link.
DEFAULT_WAVELENGTH_M = 976e-9  # acquisition beacon band (common OGS practice)
DEFAULT_PATH_LENGTH_M = 8_000.0  # UAV / short terrestrial FSO class
DEFAULT_APERTURE_M = 0.08  # coarse receive aperture


@dataclass(frozen=True)
class AtmosphericState:
    cn2: float
    r0_m: float
    rytov_variance: float
    wander_x_urad: float
    wander_y_urad: float
    scintillation: float  # multiplicative irradiance factor (~1 mean)
    strength: float


class AtmosphericChannel:
    """Cn² → r₀ / wander / scintillation sampler driven by UI strength 0–10."""

    def __init__(
        self,
        wavelength_m: float = DEFAULT_WAVELENGTH_M,
        path_length_m: float = DEFAULT_PATH_LENGTH_M,
        aperture_m: float = DEFAULT_APERTURE_M,
        seed: int | None = None,
    ) -> None:
        self.wavelength_m = wavelength_m
        self.path_length_m = path_length_m
        self.aperture_m = aperture_m
        # None → module ``random`` so scripts/run_comparison.py frame seeds match.
        self._rng = random.Random(seed) if seed is not None else None
        self._wander_x = 0.0
        self._wander_y = 0.0
        self._scintillation = 1.0
        self.last_state = AtmosphericState(
            cn2=CN2_MIN,
            r0_m=1.0,
            rytov_variance=0.0,
            wander_x_urad=0.0,
            wander_y_urad=0.0,
            scintillation=1.0,
            strength=0.0,
        )

    def _gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        if self._rng is None:
            return random.gauss(mu, sigma)
        return self._rng.gauss(mu, sigma)

    def _gammavariate(self, alpha: float, beta: float) -> float:
        if self._rng is None:
            return random.gammavariate(alpha, beta)
        return self._rng.gammavariate(alpha, beta)

    @staticmethod
    def strength_to_cn2(strength: float) -> float:
        s = max(0.0, min(10.0, float(strength)))
        if s <= 0.0:
            return CN2_MIN
        # Log-uniform map so mid-slider is moderate, high end is strong.
        log_min = math.log10(CN2_MIN)
        log_max = math.log10(CN2_MAX)
        return 10.0 ** (log_min + (log_max - log_min) * (s / 10.0))

    def fried_r0(self, cn2: float) -> float:
        """Plane-wave Fried parameter r₀ (m) for path-integrated Cn²."""
        k = 2.0 * math.pi / self.wavelength_m
        # r0 = (0.423 k^2 Cn2 L)^(-3/5)
        arg = 0.423 * (k**2) * max(cn2, 1e-30) * self.path_length_m
        return float(arg ** (-3.0 / 5.0))

    def rytov_variance(self, cn2: float) -> float:
        """Plane-wave Rytov variance σ_R² = 1.23 Cn² k^{7/6} L^{11/6}."""
        k = 2.0 * math.pi / self.wavelength_m
        return float(
            1.23
            * max(cn2, 0.0)
            * (k ** (7.0 / 6.0))
            * (self.path_length_m ** (11.0 / 6.0))
        )

    def wander_sigma_urad(self, cn2: float, r0_m: float) -> float:
        """One-axis RMS tip/tilt / beam-wander angle (µrad).

        Uses angle-of-arrival scale ~ 0.5 λ / r0 with mild aperture averaging,
        then blends a Cn² L^{1/2} term so weak turbulence still produces jitter.
        """
        if cn2 <= CN2_MIN * 1.05:
            return 0.0
        aoa_rad = 0.5 * self.wavelength_m / max(r0_m, 1e-6)
        # Soft aperture averaging: larger D reduces tip/tilt.
        avg = (self.aperture_m / max(r0_m, 1e-6)) ** (1.0 / 6.0)
        avg = max(0.35, min(1.0, 1.0 / max(avg, 1e-6)))
        sigma_rad = aoa_rad * avg
        # Floor from residual Cn² path so mid-strength is visibly non-zero.
        floor_rad = 2.5e-6 * math.sqrt(cn2 / 1e-15) * math.sqrt(
            self.path_length_m / 8000.0
        )
        return float(max(sigma_rad, floor_rad) * 1e6)

    def sample_scintillation(self, rytov: float) -> float:
        """Irradiance multiplier with mean ≈ 1.

        Weak (σ_R² < 0.5): lognormal.
        Moderate/strong: gamma-gamma style product of two gammas (Andrews α,β).
        """
        if rytov <= 1e-6:
            return 1.0

        if rytov < 0.5:
            # Lognormal: var(ln I) = ln(1+σ_I²), σ_I² ≈ σ_R² in weak regime.
            sigma_i2 = min(rytov, 0.49)
            sigma_ln = math.sqrt(math.log(1.0 + sigma_i2))
            mu_ln = -0.5 * sigma_ln * sigma_ln
            return float(math.exp(self._gauss(mu_ln, sigma_ln)))

        # Gamma-gamma parameters (simplified Andrews mapping).
        sigma_i2 = min(rytov / (1.0 + 0.5 * rytov), 4.0)
        # α, β from moments; clamp for numerical stability.
        alpha = 1.0 / max(math.exp(0.49 * sigma_i2 / (1.0 + 1.11 * sigma_i2**1.25) ** (7.0 / 6.0)) - 1.0, 0.05)
        beta = 1.0 / max(math.exp(0.51 * sigma_i2 / (1.0 + 0.69 * sigma_i2**1.25) ** (5.0 / 6.0)) - 1.0, 0.05)
        alpha = max(0.5, min(alpha, 50.0))
        beta = max(0.5, min(beta, 50.0))
        # Two unit-mean gammas → product mean 1.
        try:
            i1 = self._gammavariate(alpha, 1.0 / alpha)
            i2 = self._gammavariate(beta, 1.0 / beta)
            return float(max(0.02, min(i1 * i2, 5.0)))
        except ValueError:
            return 1.0

    def update(self, strength: float, dt: float) -> AtmosphericState:
        """Advance temporally correlated wander and scintillation."""
        cn2 = self.strength_to_cn2(strength)
        r0 = self.fried_r0(cn2)
        rytov = self.rytov_variance(cn2)
        sigma_urad = self.wander_sigma_urad(cn2, r0)

        # AR(1) tip/tilt: Greenwood-ish correlation ~ tens of ms.
        alpha = 0.85 ** max(dt * 60.0, 1e-6)
        innov = sigma_urad * math.sqrt(max(1.0 - alpha * alpha, 0.0))
        self._wander_x = alpha * self._wander_x + innov * self._gauss(0.0, 1.0)
        self._wander_y = alpha * self._wander_y + innov * self._gauss(0.0, 1.0)

        # Scintillation updates slower than tip/tilt (aperture averaging).
        scint_alpha = 0.70 ** max(dt * 60.0, 1e-6)
        target_i = self.sample_scintillation(rytov)
        self._scintillation = (
            scint_alpha * self._scintillation + (1.0 - scint_alpha) * target_i
        )
        self._scintillation = float(max(0.05, min(self._scintillation, 4.0)))

        if strength <= 0.0:
            self._wander_x = 0.0
            self._wander_y = 0.0
            self._scintillation = 1.0
            rytov = 0.0

        self.last_state = AtmosphericState(
            cn2=cn2,
            r0_m=r0,
            rytov_variance=rytov,
            wander_x_urad=self._wander_x,
            wander_y_urad=self._wander_y,
            scintillation=self._scintillation,
            strength=float(strength),
        )
        return self.last_state
