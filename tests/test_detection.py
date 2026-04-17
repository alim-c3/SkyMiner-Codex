import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import Candidate, PeriodicityResult, ValidationResult
from skyminer.detection.anomaly import compute_anomaly
from skyminer.detection.scoring import score_candidate


def test_anomaly_zscore_flags_outlier_row() -> None:
    cfg = SkyMinerConfig()
    rows = [{"mean": 0.0, "std": 1.0, "amplitude_p95_p5": 1.0} for _ in range(10)]
    rows.append({"mean": 50.0, "std": 1.0, "amplitude_p95_p5": 1.0})
    out = compute_anomaly(rows, cfg)
    assert len(out) == len(rows)
    assert out[-1]["zscore_score"] > out[0]["zscore_score"]


def test_scoring_combines_components() -> None:
    cfg = SkyMinerConfig()
    cand = Candidate(
        candidate_id=Candidate.build_id("local_sample", "t"),
        target_id="t",
        source="local_sample",
        features={"amplitude_p95_p5": 3.0},
        periodicity=PeriodicityResult(dominant_period_days=1.0, power=1.0, quality=0.8),
        anomaly={"zscore_score": 2.0},
        validation=ValidationResult(status="no_match"),
    )
    s = score_candidate(cand, cfg)
    assert 0.0 <= s.total <= 1.0
    assert s.total > 0.2
