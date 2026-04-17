from __future__ import annotations

import logging

import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import LightCurve

log = logging.getLogger(__name__)


def clean_lightcurve(lc: LightCurve, cfg: SkyMinerConfig) -> LightCurve:
    """Clean a light curve.

    Steps:
    - Remove NaNs/infs (common in photometry products and joins).
    - Sort by time (required for autocorrelation/period searches).
    - Optional smoothing for visualization and robustness.

    Scientific tradeoffs:
    - Smoothing can attenuate sharp transient features and distort shallow eclipses.
    - For discovery pipelines, keep smoothing configurable and apply lightly.
    """

    t, y, e = lc.as_arrays()
    mask = np.isfinite(t) & np.isfinite(y)
    if e is not None:
        mask &= np.isfinite(e)
    t = t[mask]
    y = y[mask]
    e = None if e is None else e[mask]

    if len(t) < 5:
        raise ValueError(f"Too few points after cleaning for {lc.target_id}")

    order = np.argsort(t)
    t = t[order]
    y = y[order]
    e = None if e is None else e[order]

    if cfg.preprocessing.smoothing.enabled and cfg.preprocessing.smoothing.method == "savgol":
        y = _savgol_safe(
            y,
            window_length=cfg.preprocessing.smoothing.window_length,
            polyorder=cfg.preprocessing.smoothing.polyorder,
        )

    return lc.model_copy(
        update={
            "time": t.astype(float).tolist(),
            "flux": y.astype(float).tolist(),
            "flux_err": None if e is None else e.astype(float).tolist(),
        }
    )


def _savgol_safe(y: np.ndarray, *, window_length: int, polyorder: int) -> np.ndarray:
    try:
        from scipy.signal import savgol_filter  # type: ignore
    except Exception:
        return y
    if len(y) < 7:
        return y
    wl = int(window_length)
    if wl % 2 == 0:
        wl += 1
    wl = max(5, min(wl, len(y) - (1 - (len(y) % 2))))
    if wl <= polyorder + 2:
        return y
    try:
        return savgol_filter(y, window_length=wl, polyorder=int(polyorder), mode="interp")
    except Exception:
        log.warning("Savgol smoothing failed; leaving series unchanged.")
        return y
