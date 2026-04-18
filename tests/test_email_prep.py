from __future__ import annotations

import uuid
from pathlib import Path

from skyminer.config import SkyMinerConfig
from skyminer.pipeline.runner import run_pipeline
from skyminer.reporting.email_prep import prepare_email_packet


def test_prepare_email_packet_creates_files() -> None:
    scratch = Path.home() / "skyminer_test_tmp" / f"email_{uuid.uuid4().hex}"
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
    res = run_pipeline(cfg, mode="local", tic_ids=None, coords=None, max_targets=1, validate=False)
    pkt = prepare_email_packet(cfg, run_id=str(res["run_id"]), max_candidates=3)
    assert pkt.draft_txt.exists()
    assert pkt.recipients_md.exists()
    assert pkt.manifest_json.exists()

