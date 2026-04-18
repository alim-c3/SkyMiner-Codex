from __future__ import annotations

import uuid
from pathlib import Path

from skyminer.config import SkyMinerConfig
from skyminer.pipeline.runner import run_pipeline
from skyminer.reporting.dashboard import generate_dashboard


def test_generate_dashboard_creates_file() -> None:
    scratch = Path.home() / "skyminer_test_tmp" / f"dash_{uuid.uuid4().hex}"
    scratch.mkdir(parents=True, exist_ok=True)

    cfg = SkyMinerConfig().model_copy(
        update={
            "mode": "local",
            "paths": SkyMinerConfig().paths.model_copy(
                update={
                    "data_dir": Path(__file__).resolve().parents[1] / "data",
                    "outputs_dir": scratch / "outputs",
                    "db_path": scratch / "outputs" / "skyminer.sqlite",
                }
            ),
        }
    )
    run_pipeline(cfg, mode="local", tic_ids=None, coords=None, max_targets=1, validate=False)
    p = generate_dashboard(cfg)
    assert p.exists()

