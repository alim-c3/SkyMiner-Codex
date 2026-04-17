from pathlib import Path
import uuid

from skyminer.config import SkyMinerConfig
from skyminer.pipeline.runner import run_pipeline


def test_smoke_local() -> None:
    # Minimal config for local mode.
    scratch = Path.home() / "skyminer_test_tmp" / f"smoke_{uuid.uuid4().hex}"
    scratch.mkdir(parents=True, exist_ok=True)
    cfg = SkyMinerConfig()
    cfg = cfg.model_copy(
        update={
            "mode": "local",
            "paths": cfg.paths.model_copy(
                update={
                    "data_dir": Path(__file__).resolve().parents[1] / "data",
                    "outputs_dir": scratch / "outputs",
                    "db_path": scratch / "outputs" / "skyminer.sqlite",
                }
            ),
        }
    )
    res = run_pipeline(cfg, mode="local", tic_ids=None, coords=None, max_targets=1, validate=False)
    assert res["targets_ingested"] == 1
    assert Path(res["db_path"]).exists()
