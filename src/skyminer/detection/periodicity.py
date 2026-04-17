from __future__ import annotations

import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import LightCurve, PeriodicityResult
from skyminer.features.timeseries import _lomb_scargle_dominant


def estimate_periodicity(lc: LightCurve, cfg: SkyMinerConfig) -> PeriodicityResult:
    """Estimate dominant periodicity using Lomb–Scargle.

    Returns a conservative heuristic quality score in [0,1], not a formal significance.
    """

    t, y, _ = lc.as_arrays()
    period, power = _lomb_scargle_dominant(t, y, cfg)
    if period is None or power is None or not np.isfinite(power):
        return PeriodicityResult(dominant_period_days=None, power=None, quality=0.0, notes="insufficient data")

    # Heuristic: normalize power by median power proxy when available.
    # We avoid expensive bootstrap here; this is MVP scoring only.
    quality = float(np.tanh(max(0.0, power)))
    return PeriodicityResult(dominant_period_days=float(period), power=float(power), quality=quality)

