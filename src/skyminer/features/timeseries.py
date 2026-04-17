from __future__ import annotations

import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import LightCurve


def extract_features(lc: LightCurve, cfg: SkyMinerConfig) -> dict[str, float]:
    """Compute a compact feature vector for a light curve.

    Robustness goals:
    - Avoid blowing up on short series
    - Produce finite outputs whenever possible
    - Keep features interpretable
    """

    t, y, _ = lc.as_arrays()
    n = float(len(y))
    mean = float(np.mean(y))
    median = float(np.median(y))
    std = float(np.std(y))
    var = float(np.var(y))
    mad = float(np.median(np.abs(y - median)))
    amp = float(np.percentile(y, 95) - np.percentile(y, 5))

    sk = float(_skew(y)) if len(y) >= 8 else 0.0
    ku = float(_kurtosis_excess(y)) if len(y) >= 8 else 0.0

    feats: dict[str, float] = {
        "n_points": n,
        "mean": mean,
        "median": median,
        "std": std,
        "var": var,
        "mad": mad,
        "amplitude_p95_p5": amp,
        "skew": sk,
        "kurtosis": ku,
    }

    # Autocorrelation at configured lags (simple normalized).
    y0 = y - mean
    denom = float(np.dot(y0, y0)) or 1.0
    for lag in cfg.features.autocorr_lags:
        if lag <= 0 or lag >= len(y0):
            feats[f"autocorr_lag_{lag}"] = 0.0
            continue
        num = float(np.dot(y0[:-lag], y0[lag:]))
        feats[f"autocorr_lag_{lag}"] = num / denom

    # Peaks/troughs: count based on prominence in normalized series.
    # Peaks/troughs: if SciPy is available, use find_peaks; otherwise use a simple derivative sign-change count.
    feats["n_peaks"], feats["n_troughs"] = _peak_trough_counts(y, prominence=float(cfg.features.peak_prominence))

    # Lomb–Scargle summary (dominant period/power); use astropy for correctness.
    period, power = _lomb_scargle_dominant(t, y, cfg)
    feats["ls_dominant_period_days"] = float(period) if period is not None else np.nan
    feats["ls_max_power"] = float(power) if power is not None else np.nan

    # Ensure all finite (replace NaN with 0 for ML usage, but keep period/power as NaN in features).
    for k, v in list(feats.items()):
        if k.startswith("ls_"):
            continue
        if not np.isfinite(v):
            feats[k] = 0.0
    return feats


def _lomb_scargle_dominant(
    t: np.ndarray, y: np.ndarray, cfg: SkyMinerConfig
) -> tuple[float | None, float | None]:
    try:
        from astropy.timeseries import LombScargle
    except Exception:
        return None, None


def _skew(y: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    mu = float(np.mean(y))
    s = float(np.std(y))
    if s == 0:
        return 0.0
    z = (y - mu) / s
    return float(np.mean(z**3))


def _kurtosis_excess(y: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    mu = float(np.mean(y))
    s = float(np.std(y))
    if s == 0:
        return 0.0
    z = (y - mu) / s
    return float(np.mean(z**4) - 3.0)


def _peak_trough_counts(y: np.ndarray, *, prominence: float) -> tuple[float, float]:
    y = np.asarray(y, dtype=float)
    if len(y) < 10:
        return 0.0, 0.0
    try:
        from scipy.signal import find_peaks  # type: ignore

        p, _ = find_peaks(y, prominence=prominence)
        t, _ = find_peaks(-y, prominence=prominence)
        return float(len(p)), float(len(t))
    except Exception:
        dy = np.diff(y)
        # Peak if derivative switches + to -, trough if - to +.
        sign = np.sign(dy)
        sign[sign == 0] = 1
        switches = np.diff(sign)
        peaks = int(np.sum(switches < 0))
        troughs = int(np.sum(switches > 0))
        return float(peaks), float(troughs)

    if len(t) < 15:
        return None, None

    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    t_span = float(np.max(t) - np.min(t))
    if not np.isfinite(t_span) or t_span <= 0:
        return None, None

    min_p = float(cfg.features.lomb_scargle.min_period_days)
    max_p = float(cfg.features.lomb_scargle.max_period_days)
    if max_p <= min_p:
        max_p = min_p * 10

    min_f = 1.0 / max_p
    max_f = 1.0 / min_p
    try:
        freq, power = LombScargle(t, y).autopower(
            minimum_frequency=min_f,
            maximum_frequency=max_f,
            samples_per_peak=int(cfg.features.lomb_scargle.samples_per_peak),
        )
        if len(power) == 0:
            return None, None
        idx = int(np.nanargmax(power))
        best_f = float(freq[idx])
        if best_f <= 0:
            return None, None
        best_p = 1.0 / best_f
        return best_p, float(power[idx])
    except Exception:
        return None, None
