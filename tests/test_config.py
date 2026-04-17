from pathlib import Path
import uuid

from skyminer.config import SkyMinerConfig


def test_load_config() -> None:
    # Avoid pytest tmpdir machinery (blocked in this environment); write under the user profile instead.
    scratch = Path.home() / "skyminer_test_tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    cfg_path = scratch / f"cfg_{uuid.uuid4().hex}.yaml"
    cfg_path.write_text(
        """
mode: local
paths:
  data_dir: data
  outputs_dir: outputs
  db_path: outputs/test.sqlite
logging:
  level: DEBUG
""",
        encoding="utf-8",
    )
    cfg = SkyMinerConfig.load(cfg_path)
    assert cfg.mode == "local"
    assert cfg.logging.level == "DEBUG"
