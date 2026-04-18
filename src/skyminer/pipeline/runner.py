from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import Candidate, LightCurve, PipelineRun, SkyCoordLike
from skyminer.utils.io import ensure_dir, read_csv_lightcurve

log = logging.getLogger(__name__)


def run_pipeline(
    cfg: SkyMinerConfig,
    *,
    mode: str,
    tic_ids: list[str] | None,
    coords: list[tuple[float, float]] | None,
    max_targets: int,
    validate: bool,
    detect: bool = True,
    report: bool = True,
    persist: bool = True,
) -> dict[str, Any]:
    """Run the end-to-end pipeline.

    Mode A (live): uses TESS + astroquery if installed and network is available.
    Mode B (local): uses bundled sample data for deterministic offline runs.
    """

    run = PipelineRun(
        run_id=str(uuid.uuid4()),
        mode="live" if mode == "live" else "local",
        config_path=str(cfg),
        params={"tic_ids": tic_ids, "coords": coords, "max_targets": max_targets},
    )

    outputs_dir = ensure_dir(cfg.paths.outputs_dir)
    ensure_dir(outputs_dir / "logs")
    ensure_dir(outputs_dir / "plots")
    ensure_dir(outputs_dir / "reports")
    ensure_dir(outputs_dir / "candidates")

    # Lazy imports to keep local mode lightweight.
    from skyminer.persistence.database import Database
    from skyminer.persistence.repositories import Repositories

    db = Database(cfg.paths.db_path)
    repos = Repositories(db)
    repos.init_schema()

    if persist:
        repos.insert_pipeline_run(run)

    lightcurves = _ingest(cfg, mode=mode, tic_ids=tic_ids, coords=coords, max_targets=max_targets)
    if persist:
        for lc in lightcurves:
            repos.upsert_target(lc)

    candidates: list[Candidate] = []
    lightcurves_by_candidate_id: dict[str, LightCurve] = {}
    if detect:
        candidates, lightcurves_by_candidate_id = _detect_and_score(cfg, lightcurves)

    if validate and candidates:
        candidates = _validate(cfg, candidates)

    if detect and candidates:
        if persist:
            for cand in candidates:
                repos.upsert_candidate(run.run_id, cand)

        ranked = sorted([c for c in candidates if c.score is not None], key=lambda c: c.score.total, reverse=True)
        ranked_path = outputs_dir / "candidates" / f"ranked_{run.run_id}.json"
        ranked_payload = [c.model_dump() for c in ranked]
        ranked_path.write_text(json.dumps(ranked_payload, indent=2, default=str), encoding="utf-8")
        log.info("Wrote ranked candidates: %s", ranked_path)

    artifacts: dict[str, Any] = {}
    if report and candidates:
        from skyminer.reporting.report_generator import generate_reports

        top_k = min(cfg.pipeline.top_k_reports, len(candidates))
        artifacts = generate_reports(
            cfg, candidates, top_k=top_k, lightcurves_by_candidate_id=lightcurves_by_candidate_id
        )

    # Always write a plain-English run summary, even if ingestion failed or produced no candidates.
    from skyminer.reporting.run_summary import CandidateArtifacts, write_run_summary

    ranked_path = None
    try:
        ranked_path = outputs_dir / "candidates" / f"ranked_{run.run_id}.json"
        if not ranked_path.exists():
            ranked_path = None
    except Exception:
        ranked_path = None

    artifact_objs: dict[str, CandidateArtifacts] = {}
    for cid, a in (artifacts or {}).items():
        artifact_objs[cid] = CandidateArtifacts(
            candidate_id=cid,
            report_md=Path(a["report_md"]) if a.get("report_md") else None,
            report_json=Path(a["report_json"]) if a.get("report_json") else None,
            plot_lightcurve=Path(a["plot_lightcurve"]) if a.get("plot_lightcurve") else None,
            plot_periodogram=Path(a["plot_periodogram"]) if a.get("plot_periodogram") else None,
        )

    write_run_summary(
        cfg,
        run_id=run.run_id,
        mode=mode,
        targets_ingested=len(lightcurves),
        candidates=candidates,
        ranked_candidates_path=ranked_path,
        artifacts=artifact_objs,
    )

    # Generate/update the static dashboard (best-effort; never fail the pipeline for UI).
    try:
        from skyminer.reporting.dashboard import generate_dashboard

        generate_dashboard(cfg)
    except Exception:
        pass

    return {
        "run_id": run.run_id,
        "mode": mode,
        "targets_ingested": len(lightcurves),
        "candidates_scored": len([c for c in candidates if c.score is not None]),
        "outputs_dir": str(outputs_dir),
        "db_path": str(cfg.paths.db_path),
    }


def _ingest(
    cfg: SkyMinerConfig,
    *,
    mode: str,
    tic_ids: list[str] | None,
    coords: list[tuple[float, float]] | None,
    max_targets: int,
) -> list[LightCurve]:
    if mode != "live":
        sample_path = cfg.paths.data_dir / "raw" / "sample_lightcurve.csv"
        lc = read_csv_lightcurve(sample_path, target_id="LOCAL_SAMPLE_1")
        return [lc]

    from skyminer.ingestion.tess import TessIngestor

    ingestor = TessIngestor(cfg)
    results: list[LightCurve] = []

    if tic_ids is not None:
        for tic in tic_ids[:max_targets]:
            results.extend(ingestor.ingest_tic_ids([tic]))
        return results

    if coords is not None:
        coords = coords[:max_targets]
        results.extend(ingestor.ingest_coordinates(coords))
        return results

    # Reasonable live default: fall back to a short built-in TIC sample (still conservative).
    fallback = ["25155310", "383553764"]
    log.warning("No TIC IDs/coords provided; using fallback TIC IDs: %s", fallback)
    results.extend(ingestor.ingest_tic_ids(fallback))
    return results


def _detect_and_score(
    cfg: SkyMinerConfig, lightcurves: list[LightCurve]
) -> tuple[list[Candidate], dict[str, LightCurve]]:
    from skyminer.preprocessing.cleaning import clean_lightcurve
    from skyminer.preprocessing.normalization import normalize_lightcurve
    from skyminer.features.timeseries import extract_features
    from skyminer.detection.periodicity import estimate_periodicity
    from skyminer.detection.anomaly import compute_anomaly
    from skyminer.detection.scoring import score_candidate

    candidates: list[Candidate] = []
    feature_rows: list[dict[str, float]] = []
    lc_by_cid: dict[str, LightCurve] = {}

    prepped: list[tuple[LightCurve, dict[str, float], Any]] = []
    for lc in lightcurves:
        try:
            cleaned = clean_lightcurve(lc, cfg)
            normed = normalize_lightcurve(cleaned, cfg)
            feats = extract_features(normed, cfg)
            per = estimate_periodicity(normed, cfg)
            prepped.append((normed, feats, per))
            feature_rows.append(feats)
        except Exception as exc:
            log.exception("Feature extraction failed for %s: %s", lc.target_id, exc)

    if not prepped:
        return [], {}

    anomaly_bundle = compute_anomaly(feature_rows, cfg)
    for idx, (lc, feats, per) in enumerate(prepped):
        coord = None
        if lc.coord is not None:
            coord = SkyCoordLike(ra_deg=lc.coord.ra_deg, dec_deg=lc.coord.dec_deg)
        cand = Candidate(
            candidate_id=f"{lc.source}:{lc.target_id}",
            target_id=lc.target_id,
            source=lc.source,
            coord=coord,
            features=feats,
            periodicity=per,
            anomaly=anomaly_bundle[idx],
        )
        cand.score = score_candidate(cand, cfg)
        candidates.append(cand)
        lc_by_cid[cand.candidate_id] = lc

    # Deterministic ordering for ties.
    candidates.sort(key=lambda c: (-(c.score.total if c.score else 0.0), c.candidate_id))
    return candidates, lc_by_cid


def _validate(cfg: SkyMinerConfig, candidates: list[Candidate]) -> list[Candidate]:
    from skyminer.validation.catalogs import CatalogValidator

    validator = CatalogValidator(cfg)
    for cand in candidates:
        try:
            cand.validation = validator.validate(cand)
        except Exception as exc:
            log.exception("Validation failed for %s: %s", cand.candidate_id, exc)
    return candidates
