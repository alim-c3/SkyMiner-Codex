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

    args = parser.parse_args(argv)
    cfg = _load_config(Path(args.config))

    if args.cmd == "smoke-test":
        res = run_pipeline(cfg, mode="local", tic_ids=None, coords=None, max_targets=1, validate=False)
        print(json.dumps(res, indent=2, default=str))
        return

    mode = (args.mode or cfg.mode).strip()
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


def _load_config(config_path: Path) -> SkyMinerConfig:
    cfg = SkyMinerConfig.load(config_path)
    repo_root = config_path.parent.parent if config_path.parts[-2:] == ("config", config_path.name) else Path.cwd()
    cfg = cfg.resolve_paths(repo_root=repo_root.resolve())
    setup_logging(cfg.logging.level, cfg.paths.outputs_dir / "logs" / cfg.logging.file_name)
    return cfg
