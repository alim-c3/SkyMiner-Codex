from __future__ import annotations

from pathlib import Path

import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import Candidate, LightCurve


def plot_lightcurve(cfg: SkyMinerConfig, lc: LightCurve, *, out_path: Path) -> Path:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        # Plotting is optional in minimal environments; reports still include JSON/MD.
        return out_path

    t, y, _ = lc.as_arrays()
    t, y = _downsample_xy(t, y, max_points=cfg.reporting.max_points_plot)

    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(t, y, lw=0.8)
    ax.set_xlabel("Time (days)")
    ax.set_ylabel("Flux (normalized)")
    ax.set_title(f"Light Curve: {lc.source}:{lc.target_id}")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def plot_periodogram(cfg: SkyMinerConfig, lc: LightCurve, *, out_path: Path) -> Path | None:
    if not cfg.reporting.include_periodogram:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        from astropy.timeseries import LombScargle
    except Exception:
        return None

    t, y, _ = lc.as_arrays()
    if len(t) < 15:
        return None

    min_p = float(cfg.features.lomb_scargle.min_period_days)
    max_p = float(cfg.features.lomb_scargle.max_period_days)
    min_f = 1.0 / max_p
    max_f = 1.0 / min_p

    freq, power = LombScargle(t, y).autopower(
        minimum_frequency=min_f,
        maximum_frequency=max_f,
        samples_per_peak=int(cfg.features.lomb_scargle.samples_per_peak),
    )
    period = 1.0 / freq

    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(period, power, lw=0.8)
    ax.set_xlabel("Period (days)")
    ax.set_ylabel("Lomb–Scargle Power")
    ax.set_title(f"Periodogram: {lc.source}:{lc.target_id}")
    ax.set_xscale("log")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def _downsample_xy(x: np.ndarray, y: np.ndarray, *, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    if len(x) <= max_points:
        return x, y
    idx = np.linspace(0, len(x) - 1, num=max_points).astype(int)
    return x[idx], y[idx]
