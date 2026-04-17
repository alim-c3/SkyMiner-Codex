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

    html_path = reports_dir / f"run_summary_{run_id}.html"
    json_path = reports_dir / f"run_summary_{run_id}.json"

    html_path.write_text(
        _render_html(
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
    return html_path


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


def _why_not_interesting_short(c: Candidate, *, min_score: float) -> str:
    """Layperson-friendly short reason for why this candidate did not make the cut."""

    bits: list[str] = []
    score = float(c.score.total) if c.score else 0.0
    bits.append(f"below threshold (score {score:.3f} < {min_score:.3f})")

    amp = float(c.features.get("amplitude_p95_p5", 0.0) or 0.0)
    if amp < 1.0:
        bits.append("low-to-moderate variability")

    if not c.periodicity.dominant_period_days or c.periodicity.quality < 0.6:
        bits.append("no strong repeating cycle detected")

    z = float(c.anomaly.get("zscore_score", 0.0) or 0.0)
    if z < 1.0:
        bits.append("not a strong outlier versus this batch")

    if c.validation.status == "known":
        bits.append("catalog match suggests it is already known")

    return "; ".join(bits)

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


def _render_html(
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
    scored = [c for c in candidates if c.score is not None]

    def file_link(p: Path | None, label: str) -> str:
        if p is None:
            return f"<span class='na'>{label}: N/A</span>"
        try:
            uri = p.resolve().as_uri()
        except Exception:
            uri = str(p)
        return f"<a href='{uri}' target='_blank' rel='noopener noreferrer'>{label}</a>"

    def img_tag(p: Path | None, alt: str) -> str:
        if p is None:
            return ""
        try:
            uri = p.resolve().as_uri()
        except Exception:
            uri = str(p)
        return f"<div class='imgwrap'><img src='{uri}' alt='{alt}' /></div>"

    def art_lines(cid: str) -> str:
        a = artifacts.get(cid)
        if a is None:
            return "<div class='artifacts'><span class='na'>Artifacts: not found</span></div>"
        parts = [
            file_link(a.report_md, "Candidate report (HTML/MD)"),
            file_link(a.report_json, "Candidate JSON"),
            file_link(a.plot_lightcurve, "Light curve plot (PNG)") if a.plot_lightcurve else "<span class='na'>Light curve plot: N/A</span>",
            file_link(a.plot_periodogram, "Periodogram plot (PNG)") if a.plot_periodogram else "<span class='na'>Periodogram plot: N/A</span>",
        ]
        imgs = img_tag(a.plot_lightcurve, "Light curve plot") + img_tag(a.plot_periodogram, "Periodogram plot")
        return "<div class='artifacts'>" + " | ".join(parts) + "</div>" + imgs

    def candidate_block(c: Candidate) -> str:
        score = float(c.score.total) if c.score else None
        novelty = _novelty_likelihood(c)
        why = _why_interesting_short(c)
        next_steps = _next_steps(c, mode=mode)
        return f"""
        <section class="candidate">
          <h3>{c.candidate_id}</h3>
          <ul>
            <li><b>Score (0..1):</b> {f"{score:.3f}" if score is not None else "N/A"}</li>
            <li><b>Validation:</b> <code>{c.validation.status}</code></li>
            <li><b>Why it stood out:</b> {why}</li>
            <li><b>Novelty likelihood (conservative):</b> <b>{novelty['label']}</b> (heuristic {novelty['heuristic_score_0_to_1']})</li>
          </ul>
          {art_lines(c.candidate_id)}
          <details>
            <summary><b>How to read the plots (layperson-friendly)</b></summary>
            <p><b>Light curve:</b> this is a brightness-over-time line. If it goes up and down in a repeating way, that often means a variable star.</p>
            <p><b>Periodogram:</b> this chart searches for repeating cycles. A tall peak suggests a likely cycle length (period). A clearer peak usually means a more reliable repeating signal.</p>
          </details>
          <details open>
            <summary><b>Next steps</b></summary>
            <ul>
              {''.join(f'<li>{s[2:]}</li>' for s in next_steps.splitlines() if s.startswith('- '))}
            </ul>
          </details>
        </section>
        """

    ranked_line = f"`{ranked_candidates_path}`" if ranked_candidates_path else "N/A"

    ranked_href = ranked_candidates_path.resolve().as_uri() if ranked_candidates_path else ""
    rejected_items = (
        "".join(
            f"<li><code>{c.candidate_id}</code> - {_why_not_interesting_short(c, min_score=min_score)}</li>"
            for c in rejected
        )
        if rejected
        else "<li>None in this run.</li>"
    )
    interesting_blocks = (
        "".join(candidate_block(c) for c in interesting)
        if interesting
        else "<p>None met the interesting threshold in this run.</p>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SkyMiner Run Summary {run_id}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; color: #111; }}
    code {{ background: #f4f4f6; padding: 1px 4px; border-radius: 4px; }}
    .meta {{ background: #f7fafc; border: 1px solid #e2e8f0; padding: 12px 14px; border-radius: 10px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .kpi {{ background: #fff; border: 1px solid #e5e7eb; padding: 10px 12px; border-radius: 10px; }}
    .candidate {{ border: 1px solid #e5e7eb; border-radius: 12px; padding: 12px 14px; margin: 14px 0; }}
    .artifacts {{ margin: 8px 0; font-size: 0.95em; }}
    .imgwrap img {{ max-width: 100%; height: auto; border: 1px solid #e5e7eb; border-radius: 10px; margin: 8px 0; }}
    .na {{ color: #6b7280; }}
    details {{ margin-top: 8px; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <h1>SkyMiner Run Summary</h1>
  <div class="meta">
    <div><b>Run ID:</b> <code>{run_id}</code></div>
    <div><b>Mode:</b> <code>{mode}</code></div>
    <div><b>Generated at (UTC):</b> <code>{generated_at}</code></div>
    <div><b>Ranked candidates JSON:</b> {f"<a href='{ranked_href}'>open</a>" if ranked_href else "N/A"}</div>
  </div>

  <h2>What happened (plain English)</h2>
  <p>
    SkyMiner downloaded/loaded <b>{targets_ingested}</b> piece(s) of time-series data (light curves) and analyzed them for
    <b>variability</b> (brightness changing over time), <b>periodicity</b> (repeating patterns), and <b>anomaly signals</b>
    (unusual behavior compared to the rest of the batch). It then tried to cross-check against public catalogs when possible.
  </p>

  <div class="grid">
    <div class="kpi"><b>Targets ingested</b><div>{targets_ingested}</div></div>
    <div class="kpi"><b>Candidates scored</b><div>{len(scored)}</div></div>
    <div class="kpi"><b>Interesting</b><div>{len(interesting)}</div></div>
    <div class="kpi"><b>Rejected</b><div>{len(rejected)}</div></div>
  </div>

  <h2>Not interesting (rejected)</h2>
  <p>Rejected means the candidate scored below the configured interesting threshold (score &lt; {min_score}).</p>
  <ul>
    {rejected_items}
  </ul>

  <h2>Interesting candidates</h2>
  <p>
    "Interesting" means: score &ge; {min_score}. This is a prioritization rule, not a scientific confirmation.
    If a candidate is marked "no match" in catalogs, that only means "no obvious match found" in the catalogs queried by this run.
  </p>
  {interesting_blocks}

  <h2>Notes and cautions</h2>
  <ul>
    <li>SkyMiner outputs are <b>candidates</b>, not confirmed discoveries.</li>
    <li>Catalog checks can miss matches due to coordinate uncertainty, proper motion, or catalog incompleteness.</li>
    <li>A "no match" result is <b>not proof</b> something is new; it is only a signal to prioritize follow-up.</li>
  </ul>
</body>
</html>
"""


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
