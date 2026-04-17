from pathlib import Path

from skyminer.config import SkyMinerConfig


def test_load_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.yaml"
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

