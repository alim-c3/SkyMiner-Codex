from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import Candidate


@dataclass(frozen=True)
class CandidateArtifacts:
    candidate_id: str
    report_md: Path | None
    report_json: Path | None
    plot_lightcurve: Path | None
    plot_periodogram: Path | None


def write_run_summary(
    cfg: SkyMinerConfig,
    *,
    run_id: str,
    mode: str,
    targets_ingested: int,
    candidates: list[Candidate],
    ranked_candidates_path: Path | None,
    artifacts: dict[str, CandidateArtifacts],
) -> Path:
    """Write a small human-readable summary of what happened in a run.

    This is aimed at a layperson first, while preserving key technical details.
    """

    min_score = float(cfg.detection.scoring.min_score_to_report)
    scored = [c for c in candidates if c.score is not None]
    interesting = [c for c in scored if c.score and c.score.total >= min_score]
    rejected = [c for c in scored if c.score and c.score.total < min_score]
    unscored = [c for c in candidates if c.score is None]

    summary = {
        "run_id": run_id,
        "mode": mode,
        "targets_ingested": targets_ingested,
        "candidates_total": len(candidates),
        "candidates_scored": len(scored),
        "candidates_interesting": len(interesting),
        "candidates_rejected": len(rejected),
        "candidates_unscored": len(unscored),
        "ranked_candidates_path": str(ranked_candidates_path) if ranked_candidates_path else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interesting": [_candidate_summary(c) for c in interesting],
        "rejected": [_candidate_summary(c) for c in rejected],
        "unscored": [c.candidate_id for c in unscored],
    }

    reports_dir = cfg.paths.outputs_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    md_path = reports_dir / f"run_summary_{run_id}.md"
    json_path = reports_dir / f"run_summary_{run_id}.json"

    md_path.write_text(
        _render_markdown(
            cfg,
            run_id=run_id,
            mode=mode,
            targets_ingested=targets_ingested,
            candidates=candidates,
            interesting=interesting,
            rejected=rejected,
            unscored=unscored,
            ranked_candidates_path=ranked_candidates_path,
            artifacts=artifacts,
        ),
        encoding="utf-8",
    )
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return md_path


def _candidate_summary(c: Candidate) -> dict[str, Any]:
    return {
        "candidate_id": c.candidate_id,
        "target_id": c.target_id,
        "source": c.source,
        "score_total": float(c.score.total) if c.score else None,
        "validation_status": c.validation.status,
        "period_days": c.periodicity.dominant_period_days,
        "period_quality": c.periodicity.quality,
        "amplitude": c.features.get("amplitude_p95_p5"),
        "why_interesting_short": _why_interesting_short(c),
        "novelty_likelihood": _novelty_likelihood(c),
    }


def _why_interesting_short(c: Candidate) -> str:
    reasons: list[str] = []
    amp = float(c.features.get("amplitude_p95_p5", 0.0) or 0.0)
    if amp >= 1.0:
        reasons.append(f"clear variability (amplitude ~ {amp:.2f})")
    if c.periodicity.quality >= 0.6 and c.periodicity.dominant_period_days:
        reasons.append(
            f"strong periodic signal (~{c.periodicity.dominant_period_days:.3f} d)"
        )
    z = float(c.anomaly.get("zscore_score", 0.0) or 0.0)
    if z >= 1.0:
        reasons.append("feature outlier(s) compared to this batch")
    if c.validation.status == "no_match":
        reasons.append("no obvious catalog match found (not proof of novelty)")
    if not reasons:
        reasons.append("moderate combined score (follow-up recommended if resources allow)")
    return "; ".join(reasons)


def _novelty_likelihood(c: Candidate) -> dict[str, Any]:
    """Conservative heuristic only. Not a scientific probability."""

    status = c.validation.status
    base_label = "Low"
    base_score = 0.2
    if status == "known_classified":
        base_label = "Very low"
        base_score = 0.02
    elif status == "known_unclear":
        base_label = "Low"
        base_score = 0.10
    elif status == "no_match":
        base_label = "Low to medium"
        base_score = 0.35
    elif status == "unknown":
        base_label = "Low"
        base_score = 0.15

    # If the candidate has no coordinates, validation is weaker.
    if c.coord is None:
        base_label = "Very low"
        base_score = min(base_score, 0.05)

    return {
        "label": base_label,
        "heuristic_score_0_to_1": base_score,
        "caution": "This is a conservative heuristic. Catalog non-matches are not proof of novelty.",
    }


def _render_markdown(
    cfg: SkyMinerConfig,
    *,
    run_id: str,
    mode: str,
    targets_ingested: int,
    candidates: list[Candidate],
    interesting: list[Candidate],
    rejected: list[Candidate],
    unscored: list[Candidate],
    ranked_candidates_path: Path | None,
    artifacts: dict[str, CandidateArtifacts],
) -> str:
    min_score = float(cfg.detection.scoring.min_score_to_report)
    generated_at = datetime.now(timezone.utc).isoformat()

    def art_lines(cid: str) -> str:
        a = artifacts.get(cid)
        if a is None:
            return "- Artifacts: not found\n"
        lines = [
            f"- Report (MD): `{a.report_md}`" if a.report_md else "- Report (MD): N/A",
            f"- Report (JSON): `{a.report_json}`" if a.report_json else "- Report (JSON): N/A",
        ]
        if a.plot_lightcurve is not None:
            lines.append(f"- Plot (light curve): `{a.plot_lightcurve}`")
        if a.plot_periodogram is not None:
            lines.append(f"- Plot (periodogram): `{a.plot_periodogram}`")
        return "\n".join(lines) + "\n"

    def candidate_block(c: Candidate) -> str:
        score = c.score.total if c.score else None
        novelty = _novelty_likelihood(c)
        why = _why_interesting_short(c)
        next_steps = _next_steps(c, mode=mode)
        return (
            f"### {c.candidate_id}\n\n"
            f"- Score (0..1): `{score:.3f}`\n"
            f"- Validation: `{c.validation.status}`\n"
            f"- Why it stood out: {why}\n"
            f"- Novelty likelihood (conservative): **{novelty['label']}** (heuristic {novelty['heuristic_score_0_to_1']})\n"
            f"{art_lines(c.candidate_id)}\n"
            f"**How to read the plots (layperson-friendly):**\n"
            f"- Light curve: the line shows how brightness changes over time. Big repeating up/down patterns often mean a variable star.\n"
            f"- Periodogram: the tallest peak suggests a repeating cycle length (period). A clear peak supports periodic variability.\n\n"
            f"**Next steps:**\n"
            f"{next_steps}\n"
        )

    ranked_line = f"`{ranked_candidates_path}`" if ranked_candidates_path else "N/A"

    md = [
        "# SkyMiner Run Summary",
        "",
        f"- Run ID: `{run_id}`",
        f"- Mode: `{mode}`",
        f"- Data analyzed: `{targets_ingested}` ingested target(s), `{len(candidates)}` candidate object(s)",
        f"- Interesting threshold: score >= `{min_score}`",
        f"- Ranked candidates JSON: {ranked_line}",
        f"- Generated at (UTC): `{generated_at}`",
        "",
        "## Results",
        "",
        f"- Interesting: `{len(interesting)}`",
        f"- Not interesting (rejected): `{len(rejected)}`",
        f"- Unscored (errors/insufficient data): `{len(unscored)}`",
        "",
        "## Not Interesting (Rejected)",
        "",
    ]

    if not rejected:
        md.append("_None in this run._")
    else:
        for c in rejected:
            md.append(f"- `{c.candidate_id}` (score {c.score.total:.3f})")

    md.extend(["", "## Interesting Candidates", ""])
    if not interesting:
        md.append("_None met the interesting threshold in this run._")
    else:
        for c in interesting:
            md.append(candidate_block(c))

    md.extend(
        [
            "",
            "## Notes and Cautions",
            "",
            "- SkyMiner produces **candidates**, not confirmed discoveries.",
            "- Catalog checks can miss matches due to coordinate uncertainty, proper motion, or catalog incompleteness.",
            "- A \"no match\" result means only: no obvious match found in the catalogs queried by this run.",
        ]
    )
    return "\n".join(md).strip() + "\n"


def _next_steps(c: Candidate, *, mode: str) -> str:
    steps: list[str] = []
    if mode != "live":
        steps.append("- Re-run in `--mode live` for this target to validate against catalogs using real services.")
    steps.append("- Manually cross-check SIMBAD/VizieR/VSX (when integrated) using the candidate coordinates.")
    steps.append("- Inspect the light curve for instrumental artifacts or outliers driving the signal.")
    if c.periodicity.dominant_period_days:
        steps.append("- Verify the period by checking if the light curve repeats when folded on that period.")
    steps.append("- If still compelling, plan follow-up photometry and document provenance for a potential submission.")
    return "\n".join(steps)
