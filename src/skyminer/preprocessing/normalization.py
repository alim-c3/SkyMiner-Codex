from __future__ import annotations

import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import LightCurve


def normalize_lightcurve(lc: LightCurve, cfg: SkyMinerConfig) -> LightCurve:
    """Normalize flux values.

    Methods:
    - zscore: (x-mean)/std
    - robust_zscore: (x-median)/(1.4826*MAD)

    Scientific tradeoffs:
    - Z-scoring assumes roughly Gaussian noise; robust z-scoring is more stable
      when outliers or transients exist.
    """

    t, y, e = lc.as_arrays()
    method = cfg.preprocessing.normalization.method
    if method == "none":
        return lc

    if method == "zscore":
        mu = float(np.mean(y))
        sigma = float(np.std(y)) or 1.0
        yn = (y - mu) / sigma
    elif method == "robust_zscore":
        med = float(np.median(y))
        mad = float(np.median(np.abs(y - med))) or 1e-12
        scale = 1.4826 * mad
        yn = (y - med) / scale
    else:
        raise ValueError(f"Unknown normalization method: {method}")

    return lc.model_copy(update={"flux": yn.astype(float).tolist()})

