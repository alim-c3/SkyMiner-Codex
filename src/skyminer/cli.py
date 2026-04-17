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


def _load_config(config_path: Path) -> SkyMinerConfig:
    cfg = SkyMinerConfig.load(config_path)
    repo_root = config_path.parent.parent if config_path.parts[-2:] == ("config", config_path.name) else Path.cwd()
    cfg = cfg.resolve_paths(repo_root=repo_root.resolve())
    setup_logging(cfg, cfg.paths.outputs_dir)
    return cfg


if __name__ == "__main__":  # pragma: no cover
    main()
