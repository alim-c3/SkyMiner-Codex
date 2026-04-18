from __future__ import annotations

import argparse
import json
from pathlib import Path

from skyminer.config import SkyMinerConfig, default_config_path
from skyminer.logging_config import setup_logging
from skyminer.pipeline.runner import run_pipeline


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="skyminer", description="SkyMiner discovery pipeline (MVP).")
    parser.add_argument("--config", default=str(default_config_path()), help="Path to config YAML")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("smoke-test", help="Run a tiny offline pipeline run using bundled sample data.")

    p_run = sub.add_parser("run-pipeline", help="Run end-to-end pipeline (local or live).")
    p_run.add_argument("--mode", default=None, help="local or live")
    p_run.add_argument("--tic", action="append", default=[], help="TIC ID (repeatable)")
    p_run.add_argument("--ra", type=float, action="append", default=[], help="RA deg (repeatable)")
    p_run.add_argument("--dec", type=float, action="append", default=[], help="Dec deg (repeatable)")
    p_run.add_argument("--max-targets", type=int, default=8)

    p_ingest = sub.add_parser("ingest", help="Ingest only.")
    p_ingest.add_argument("--mode", default=None)
    p_ingest.add_argument("--tic", action="append", default=[])
    p_ingest.add_argument("--max-targets", type=int, default=8)

    p_val = sub.add_parser("validate", help="Ingest + validate only.")
    p_val.add_argument("--mode", default=None)
    p_val.add_argument("--tic", action="append", default=[])
    p_val.add_argument("--max-targets", type=int, default=8)

    p_rank = sub.add_parser("rank-candidates", help="Ingest + detect + score (no reporting).")
    p_rank.add_argument("--mode", default=None)
    p_rank.add_argument("--max-targets", type=int, default=8)

    p_rep = sub.add_parser("generate-report", help="Run pipeline and generate reports for top candidates.")
    p_rep.add_argument("--mode", default=None)
    p_rep.add_argument("--max-targets", type=int, default=3)

    p_last = sub.add_parser(
        "run-last-night",
        help="Live run using 'last night' MAST window: discover recent TESS time-series products and analyze them.",
    )
    p_last.add_argument("--hours", type=int, default=None, help="Lookback window in hours (UTC). Default from config.")
    p_last.add_argument(
        "--max-tics",
        type=int,
        default=None,
        help="Max TIC IDs to ingest (safety cap). Default from config.",
    )
    p_last.add_argument("--max-targets", type=int, default=None, help="Max targets to ingest (alias for max-tics).")

    p_pub = sub.add_parser(
        "run-public-sample",
        help="Live run over a reproducible public TIC sample (MAST TIC catalog) and score/rank candidates.",
    )
    p_pub.add_argument("--n", type=int, default=None, help="Number of TIC targets to sample.")
    p_pub.add_argument("--seed", type=int, default=None, help="Sampling seed.")
    p_pub.add_argument("--tmag-max", type=float, default=None, help="TESS magnitude max filter (when present).")
    p_pub.add_argument("--cone-radius-deg", type=float, default=None, help="Cone radius per random sky point (deg).")
    p_pub.add_argument("--max-query-points", type=int, default=None, help="Max random sky points to query.")
    p_pub.add_argument(
        "--tess-ingestion-mode",
        choices=["spoc", "tesscut", "spoc_then_tesscut"],
        default=None,
        help="Override TESS ingestion mode for this run.",
    )

    p_spoc = sub.add_parser(
        "run-tess-product-sample",
        help="Live run over a reproducible sample of TIC IDs that already have SPOC light curve products.",
    )
    p_spoc.add_argument("--n", type=int, default=200, help="How many ingestible TIC IDs to collect.")
    p_spoc.add_argument("--seed", type=int, default=42, help="Sampling seed.")
    p_spoc.add_argument("--max-queries", type=int, default=3000, help="Max random MAST queries while sampling.")
    p_spoc.add_argument(
        "--validate",
        action="store_true",
        help="Enable SIMBAD/VizieR validation for every candidate (slower). Default is off for harvesting.",
    )
    p_spoc.add_argument(
        "--top-k-reports",
        type=int,
        default=20,
        help="How many top candidates to generate plots/reports for. Set 0 to disable.",
    )

    p_dash = sub.add_parser("dashboard", help="Generate (or refresh) the local static dashboard HTML.")

    p_email = sub.add_parser("prepare-email", help="Prepare an email draft + attachment packet for a run_id.")
    p_email.add_argument("--run-id", required=True, help="Pipeline run id")
    p_email.add_argument("--max-candidates", type=int, default=8, help="How many top candidates to include")

    args = parser.parse_args(argv)
    cfg = _load_config(Path(args.config))

    if args.cmd == "smoke-test":
        res = run_pipeline(cfg, mode="local", tic_ids=None, coords=None, max_targets=1, validate=False)
        print(json.dumps(res, indent=2, default=str))
        return

    mode = (getattr(args, "mode", None) or cfg.mode).strip()
    if args.cmd == "run-pipeline":
        coords = list(zip(args.ra, args.dec)) if args.ra and args.dec and len(args.ra) == len(args.dec) else None
        res = run_pipeline(
            cfg,
            mode=mode,
            tic_ids=args.tic or None,
            coords=coords,
            max_targets=int(args.max_targets),
            validate=cfg.validation.enabled,
        )
        print(json.dumps(res, indent=2, default=str))
        return

    if args.cmd == "ingest":
        res = run_pipeline(
            cfg,
            mode=mode,
            tic_ids=args.tic or None,
            coords=None,
            max_targets=int(args.max_targets),
            validate=False,
            detect=False,
            report=False,
            persist=True,
        )
        print(json.dumps(res, indent=2, default=str))
        return

    if args.cmd == "validate":
        res = run_pipeline(
            cfg,
            mode=mode,
            tic_ids=args.tic or None,
            coords=None,
            max_targets=int(args.max_targets),
            validate=True,
            detect=False,
            report=False,
            persist=True,
        )
        print(json.dumps(res, indent=2, default=str))
        return

    if args.cmd == "rank-candidates":
        res = run_pipeline(
            cfg,
            mode=mode,
            tic_ids=None,
            coords=None,
            max_targets=int(args.max_targets),
            validate=cfg.validation.enabled,
            detect=True,
            report=False,
            persist=True,
        )
        print(json.dumps(res, indent=2, default=str))
        return

    if args.cmd == "generate-report":
        res = run_pipeline(
            cfg,
            mode=mode,
            tic_ids=None,
            coords=None,
            max_targets=int(args.max_targets),
            validate=cfg.validation.enabled,
            detect=True,
            report=True,
            persist=True,
        )
        print(json.dumps(res, indent=2, default=str))
        return

    if args.cmd == "run-last-night":
        from skyminer.ingestion.mast_recent import fetch_recent_tic_ids

        hours = int(args.hours) if args.hours is not None else int(cfg.recent_mast.hours)
        max_tics = (
            int(args.max_targets)
            if args.max_targets is not None
            else int(args.max_tics) if args.max_tics is not None else int(cfg.recent_mast.max_tic_ids)
        )

        recent = fetch_recent_tic_ids(cfg, hours=hours, max_tics=max_tics)
        res = run_pipeline(
            cfg,
            mode="live",
            # Important: pass an explicit list (even empty) so live mode does not fall back to default TIC IDs.
            tic_ids=recent.tic_ids,
            coords=None,
            max_targets=len(recent.tic_ids),
            validate=cfg.validation.enabled,
        )
        # Include the discovery window in stdout for convenience.
        payload = {"recent_window": recent.__dict__, "pipeline": res}
        print(json.dumps(payload, indent=2, default=str))
        return

    if args.cmd == "run-public-sample":
        from skyminer.ingestion.tic_catalog import load_or_create_tic_sample

        n = int(args.n) if args.n is not None else int(cfg.public_sample.n_targets)
        seed = int(args.seed) if args.seed is not None else int(cfg.public_sample.seed)
        tmag_max = float(args.tmag_max) if args.tmag_max is not None else float(cfg.public_sample.tmag_max)
        cone_radius_deg = (
            float(args.cone_radius_deg) if args.cone_radius_deg is not None else float(cfg.public_sample.cone_radius_deg)
        )
        max_query_points = (
            int(args.max_query_points) if args.max_query_points is not None else int(cfg.public_sample.max_query_points)
        )

        # Cache under data/catalogs so repeated runs are reproducible and cheaper.
        cache_path = cfg.paths.data_dir / "catalogs" / f"tic_sample_n{n}_seed{seed}_tmag{tmag_max:.1f}.json"
        sample = load_or_create_tic_sample(
            cfg,
            n=n,
            seed=seed,
            tmag_max=tmag_max,
            cone_radius_deg=cone_radius_deg,
            max_query_points=max_query_points,
            cache_path=cache_path,
        )

        if args.tess_ingestion_mode:
            cfg = cfg.model_copy(
                update={"tess": cfg.tess.model_copy(update={"ingestion_mode": str(args.tess_ingestion_mode)})}
            )

        res = run_pipeline(
            cfg,
            mode="live",
            tic_ids=sample.tic_ids,
            coords=None,
            max_targets=len(sample.tic_ids),
            validate=cfg.validation.enabled,
        )
        payload = {"tic_sample": sample.__dict__, "pipeline": res}
        print(json.dumps(payload, indent=2, default=str))
        return

    if args.cmd == "run-tess-product-sample":
        from skyminer.ingestion.tess_product_sample import load_or_create_tess_product_sample

        n = int(args.n)
        seed = int(args.seed)
        max_queries = int(args.max_queries)

        cache_path = cfg.paths.data_dir / "catalogs" / f"tess_spoc_sample_n{n}_seed{seed}.json"
        sample = load_or_create_tess_product_sample(
            cfg, n=n, seed=seed, max_queries=max_queries, cache_path=cache_path
        )

        # Force SPOC ingestion for this command.
        cfg = cfg.model_copy(update={"tess": cfg.tess.model_copy(update={"ingestion_mode": "spoc"})})
        cfg = cfg.model_copy(update={"pipeline": cfg.pipeline.model_copy(update={"top_k_reports": int(args.top_k_reports)})})

        res = run_pipeline(
            cfg,
            mode="live",
            tic_ids=sample.tic_ids,
            coords=None,
            max_targets=len(sample.tic_ids),
            validate=bool(args.validate) and cfg.validation.enabled,
            report=int(args.top_k_reports) > 0,
        )
        payload = {"tess_spoc_sample": sample.__dict__, "pipeline": res}
        print(json.dumps(payload, indent=2, default=str))
        return

    if args.cmd == "dashboard":
        from skyminer.reporting.dashboard import generate_dashboard

        p = generate_dashboard(cfg)
        print(json.dumps({"dashboard_path": str(p)}, indent=2))
        return

    if args.cmd == "prepare-email":
        from skyminer.reporting.email_prep import prepare_email_packet

        pkt = prepare_email_packet(cfg, run_id=str(args.run_id), max_candidates=int(args.max_candidates))
        print(
            json.dumps(
                {
                    "run_id": pkt.run_id,
                    "out_dir": str(pkt.out_dir),
                    "draft_txt": str(pkt.draft_txt),
                    "recipients_md": str(pkt.recipients_md),
                    "manifest_json": str(pkt.manifest_json),
                },
                indent=2,
            )
        )
        return


def _load_config(config_path: Path) -> SkyMinerConfig:
    cfg = SkyMinerConfig.load(config_path)
    repo_root = config_path.parent.parent if config_path.parts[-2:] == ("config", config_path.name) else Path.cwd()
    cfg = cfg.resolve_paths(repo_root=repo_root.resolve())
    setup_logging(cfg, cfg.paths.outputs_dir)
    return cfg


if __name__ == "__main__":  # pragma: no cover
    main()
