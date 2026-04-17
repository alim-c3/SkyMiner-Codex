import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import LightCurve
from skyminer.preprocessing.cleaning import clean_lightcurve
from skyminer.preprocessing.normalization import normalize_lightcurve


def test_cleaning_sorts_and_removes_nans() -> None:
    cfg = SkyMinerConfig()
    lc = LightCurve(
        source="local_sample",
        target_id="X",
        # Keep >= 5 finite points after dropping NaNs.
        time=[2.0, 1.0, 3.0, float("nan"), 4.0, 5.0, 6.0],
        flux=[1.0, 2.0, 3.0, 9.0, float("nan"), 5.0, 6.0],
        flux_err=None,
    )
    cleaned = clean_lightcurve(lc, cfg)
    t, y, _ = cleaned.as_arrays()
    assert np.all(np.diff(t) >= 0)
    assert np.all(np.isfinite(t))
    assert np.all(np.isfinite(y))


def test_normalization_robust_zscore_has_median_zeroish() -> None:
    cfg = SkyMinerConfig()
    lc = LightCurve(source="local_sample", target_id="X", time=list(range(20)), flux=[1] * 10 + [10] * 10)
    cleaned = clean_lightcurve(lc, cfg)
    normed = normalize_lightcurve(cleaned, cfg)
    _, y, _ = normed.as_arrays()
    assert abs(float(np.median(y))) < 1e-6
