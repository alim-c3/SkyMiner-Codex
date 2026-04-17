"""SkyMiner logging configuration.

Call ``setup_logging(cfg, outputs_dir)`` once at pipeline startup.  Subsequent
calls are idempotent — handlers are added only if the root logger has none yet.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from skyminer.config import SkyMinerConfig


_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(cfg: SkyMinerConfig, outputs_dir: Path) -> None:
    """Configure root logger with a StreamHandler (stderr) and a FileHandler.

    Args:
        cfg: Fully loaded ``SkyMinerConfig`` — ``cfg.logging.level`` and
             ``cfg.logging.file_name`` are read from it.
        outputs_dir: Base output directory.  The log file is written to
                     ``outputs_dir / "logs" / cfg.logging.file_name``.

    The function is idempotent: if the root logger already has handlers
    attached, no new handlers are added and the call returns immediately.
    """
    root = logging.getLogger()

    # Idempotency guard — do not add duplicate handlers.
    if root.handlers:
        return

    level = _coerce_level(cfg.logging.level)
    root.setLevel(level)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- stderr stream handler ---
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # --- file handler ---
    log_dir = outputs_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / cfg.logging.file_name

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def _coerce_level(level: str) -> int:
    """Convert a level name string (e.g. ``"INFO"``) to a ``logging`` int constant."""
    return getattr(logging, (level or "INFO").upper(), logging.INFO)
