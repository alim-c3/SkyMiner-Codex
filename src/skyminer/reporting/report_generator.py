from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import Candidate, LightCurve
from skyminer.reporting.plots import plot_lightcurve, plot_periodogram


def _render_markdown(cand: Candidate) -> str:
    features_json = json.dumps(cand.features, indent=2, default=str)
    anomaly_json = json.dumps(cand.anomaly, indent=2, default=str)
    coord = (
        f"RA={cand.coord.ra_deg:.6f}, Dec={cand.coord.dec_deg:.6f}" if cand.coord is not None else "N/A"
    )
    generated_at = datetime.now(timezone.utc).isoformat()

    return f"""# SkyMiner Candidate Report

**Candidate ID:** {cand.candidate_id}

## Summary (Conservative)

This object is a **candidate** for follow-up investigation based on variability/anomaly signals in the available photometric time series.
SkyMiner does **not** confirm discoveries. Absence of catalog matches is **not proof** of novelty.

## Source Data

- Source: {cand.source}
- Target ID: {cand.target_id}
- Coordinates (ICRS deg): {coord}

## Extracted Features

```json
{features_json}
```

## Periodicity (Lomb–Scargle)

- Dominant period (days): {cand.periodicity.dominant_period_days}
- Power: {cand.periodicity.power}
- Heuristic quality (0..1): {cand.periodicity.quality}
- Notes: {cand.periodicity.notes or ""}

## Anomaly Signals

```json
{anomaly_json}
```

## Catalog Validation

- Status: {cand.validation.status}
- Matched name: {cand.validation.matched_name or "N/A"}
- Matched type: {cand.validation.matched_type or "N/A"}
- Catalogs checked: {cand.validation.catalogs_checked}

## Why This Candidate Is Interesting

- Score (0..1): {cand.score.total if cand.score else "N/A"}
- Variability proxy (amplitude): {cand.features.get("amplitude_p95_p5")}
- Periodicity strength: {cand.periodicity.quality}

## Cautions and Limitations

- Time-series preprocessing choices (smoothing/normalization) can change apparent variability.
- Period estimates can alias with cadence or limited time baseline.
- Catalog queries can miss matches due to coordinate uncertainty, proper motion, or catalog incompleteness.

## Recommended Next Steps

1. Re-run in live mode (if available) to fetch multiple sectors/cadences for the target.
2. Cross-check additional variability catalogs (e.g., VSX) once integrated.
3. Inspect the raw light curve and systematics; verify data quality flags.
4. If still compelling, plan follow-up photometry or spectroscopy.

---

Generated at {generated_at}
"""


def generate_reports(
    cfg: SkyMinerConfig,
    candidates: list[Candidate],
    *,
    top_k: int,
    lightcurves_by_candidate_id: dict[str, LightCurve] | None = None,
) -> dict[str, dict[str, str]]:
    outputs = cfg.paths.outputs_dir
    reports_dir = outputs / "reports"
    plots_dir = outputs / "plots"
    reports_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    selected = [c for c in candidates if c.score is not None]
    selected.sort(key=lambda c: c.score.total if c.score else 0.0, reverse=True)
    selected = selected[:top_k]

    # We don't currently persist full lightcurves per candidate in DB; for MVP,
    # report generation expects local-mode sample or uses minimal placeholders.
    # Pipeline runner can be extended to pass lightcurves here.
    artifacts: dict[str, dict[str, str]] = {}
    for cand in selected:
        lc = None
        if lightcurves_by_candidate_id is not None:
            lc = lightcurves_by_candidate_id.get(cand.candidate_id)
        artifacts[cand.candidate_id] = _write_candidate_artifacts(
            cfg, cand, reports_dir=reports_dir, plots_dir=plots_dir, lc=lc
        )
    return artifacts


def _write_candidate_artifacts(
    cfg: SkyMinerConfig,
    cand: Candidate,
    *,
    reports_dir: Path,
    plots_dir: Path,
    lc: LightCurve | None,
) -> dict[str, str]:
    # JSON summary
    json_path = reports_dir / f"{_safe_name(cand.candidate_id)}.json"
    json_path.write_text(json.dumps(cand.model_dump(), indent=2, default=str), encoding="utf-8")

    # Markdown report
    md_path = reports_dir / f"{_safe_name(cand.candidate_id)}.md"
    md = _render_markdown(cand)
    md_path.write_text(md, encoding="utf-8")

    plot_lc = plots_dir / f"{_safe_name(cand.candidate_id)}_lightcurve.png"
    plot_pg = plots_dir / f"{_safe_name(cand.candidate_id)}_periodogram.png"
    if lc is not None:
        try:
            plot_lightcurve(cfg, lc, out_path=plot_lc)
            plot_periodogram(cfg, lc, out_path=plot_pg)
        except Exception:
            pass

    return {
        "report_md": str(md_path),
        "report_json": str(json_path),
        "plot_lightcurve": str(plot_lc) if plot_lc.exists() else "",
        "plot_periodogram": str(plot_pg) if plot_pg.exists() else "",
    }


def _safe_name(s: str) -> str:
    return "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in s)[:180]
