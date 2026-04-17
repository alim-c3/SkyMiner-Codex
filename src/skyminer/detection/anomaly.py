from __future__ import annotations

import numpy as np

from skyminer.config import SkyMinerConfig


def compute_anomaly(feature_rows: list[dict[str, float]], cfg: SkyMinerConfig) -> list[dict[str, object]]:
    """Compute anomaly signals for each target based on features.

    Produces interpretable outputs:
    - z-score flags for selected features (variability, skew/kurtosis, etc.)
    - optional IsolationForest score for multivariate novelty
    """

    if not feature_rows:
        return []

    keys = sorted({k for row in feature_rows for k in row.keys() if not k.startswith("ls_")})
    X = np.array([[float(row.get(k, 0.0)) for k in keys] for row in feature_rows], dtype=float)

    # Z-score heuristic per feature, aggregated into a simple score.
    mu = np.mean(X, axis=0)
    sigma = np.std(X, axis=0)
    sigma = np.where(sigma == 0, 1.0, sigma)
    Z = (X - mu) / sigma

    thresh = float(cfg.detection.anomaly.zscore_threshold)
    z_flags = np.abs(Z) >= thresh
    z_score = np.clip(np.mean(np.abs(Z), axis=1) / max(1.0, thresh), 0.0, 10.0)

    iso_score = None
    iso_label = None
    if cfg.detection.anomaly.use_isolation_forest and len(feature_rows) >= 8:
        try:
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(
                n_estimators=int(cfg.detection.anomaly.isolation_forest.n_estimators),
                contamination=float(cfg.detection.anomaly.isolation_forest.contamination),
                random_state=int(cfg.detection.anomaly.isolation_forest.random_state),
            )
            model.fit(X)
            # sklearn: lower scores -> more abnormal. We'll invert to [0,1] where 1 is more anomalous.
            raw = -model.score_samples(X)
            raw = (raw - np.min(raw)) / (np.max(raw) - np.min(raw) + 1e-12)
            iso_score = raw
            iso_label = model.predict(X)  # -1 anomaly, 1 normal
        except Exception:
            iso_score = None
            iso_label = None

    out: list[dict[str, object]] = []
    for i in range(len(feature_rows)):
        flagged = {keys[j]: bool(z_flags[i, j]) for j in range(len(keys)) if z_flags[i, j]}
        payload: dict[str, object] = {
            "zscore_threshold": thresh,
            "zscore_mean_abs": float(np.mean(np.abs(Z[i]))),
            "zscore_score": float(z_score[i]),
            "zscore_flagged_features": flagged,
        }
        if iso_score is not None and iso_label is not None:
            payload.update(
                {
                    "isolation_forest_score": float(iso_score[i]),
                    "isolation_forest_label": int(iso_label[i]),
                }
            )
        out.append(payload)
    return out

