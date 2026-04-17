from pathlib import Path

from skyminer.config import SkyMinerConfig
from skyminer.pipeline.runner import run_pipeline


def test_smoke_local(tmp_path: Path) -> None:
    # Minimal config for local mode.
    cfg = SkyMinerConfig()
    cfg = cfg.model_copy(
        update={
            "mode": "local",
            "paths": cfg.paths.model_copy(
                update={
                    "data_dir": Path(__file__).resolve().parents[1] / "data",
                    "outputs_dir": tmp_path / "outputs",
                    "db_path": tmp_path / "outputs" / "skyminer.sqlite",
                }
            ),
        }
    )
    res = run_pipeline(cfg, mode="local", tic_ids=None, coords=None, max_targets=1, validate=False)
    assert res["targets_ingested"] == 1
    assert Path(res["db_path"]).exists()

