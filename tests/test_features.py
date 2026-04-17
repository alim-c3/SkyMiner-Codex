import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import LightCurve
from skyminer.preprocessing.cleaning import clean_lightcurve
from skyminer.preprocessing.normalization import normalize_lightcurve
from skyminer.features.timeseries import extract_features


def test_extract_features_returns_expected_keys() -> None:
    cfg = SkyMinerConfig()
    t = np.linspace(0, 5, 200)
    y = np.sin(2 * np.pi * t) + 0.05 * np.random.default_rng(0).normal(size=len(t))
    lc = LightCurve(source="local_sample", target_id="X", time=t.tolist(), flux=y.tolist())
    lc = normalize_lightcurve(clean_lightcurve(lc, cfg), cfg)
    feats = extract_features(lc, cfg)
    for k in ["mean", "median", "std", "mad", "amplitude_p95_p5", "n_peaks", "ls_dominant_period_days"]:
        assert k in feats


def test_lomb_scargle_period_reasonable_on_sine() -> None:
    cfg = SkyMinerConfig()
    t = np.linspace(0, 10, 400)
    true_period = 1.0
    y = np.sin(2 * np.pi * t / true_period)
    lc = LightCurve(source="local_sample", target_id="X", time=t.tolist(), flux=y.tolist())
    feats = extract_features(lc, cfg)
    period = feats["ls_dominant_period_days"]
    assert np.isfinite(period)
    assert 0.8 <= period <= 1.2

