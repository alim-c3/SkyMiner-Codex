from __future__ import annotations

import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import Candidate, CandidateScoreBreakdown


def score_candidate(candidate: Candidate, cfg: SkyMinerConfig) -> CandidateScoreBreakdown:
    """Score candidates for ranking.

    Components:
    - anomaly: based on anomaly subsystem score(s)
    - periodicity: Lomb–Scargle quality
    - variability: amplitude proxy
    - novelty: conservative mapping from catalog validation

    Guardrail:
    - Scoring is not proof of novelty; it only prioritizes follow-up.
    """

    w = cfg.detection.scoring.weights

    anomaly = float(candidate.anomaly.get("zscore_score", 0.0))
    if "isolation_forest_score" in candidate.anomaly:
        anomaly = max(anomaly, float(candidate.anomaly.get("isolation_forest_score", 0.0)) * 3.0)
    anomaly = float(np.tanh(max(0.0, anomaly) / 2.0))

    periodicity = float(candidate.periodicity.quality or 0.0)

    amp = float(candidate.features.get("amplitude_p95_p5", 0.0))
    variability = float(np.tanh(max(0.0, amp) / 3.0))

    novelty = _novelty_from_validation(candidate.validation.status)

    total = float(
        w.anomaly * anomaly + w.periodicity * periodicity + w.variability * variability + w.novelty * novelty
    )
    total = float(np.clip(total, 0.0, 1.0))
    return CandidateScoreBreakdown(
        anomaly=anomaly,
        periodicity=periodicity,
        variability=variability,
        novelty=novelty,
        total=total,
    )


def _novelty_from_validation(status: str) -> float:
    if status == "no_match":
        return 1.0
    if status == "known_unclear":
        return 0.5
    if status == "known_classified":
        return 0.0
    return 0.2  # unknown

