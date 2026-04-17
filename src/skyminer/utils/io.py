"""SkyMiner I/O utilities."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from skyminer.models.schemas import LightCurve


def read_csv_lightcurve(
    path: Path,
    source: str = "local_sample",
    target_id: str = "sample",
) -> LightCurve:
    """Read a CSV file and return a :class:`~skyminer.models.schemas.LightCurve`.

    Expected columns: ``time``, ``flux``, and optionally ``flux_err``.  Rows
    where ``time`` or ``flux`` is NaN are dropped before constructing the object.

    Args:
        path: Absolute or relative path to the CSV file.
        source: Value for ``LightCurve.source`` (must be a valid ``Literal``).
        target_id: Identifier string stored on the returned object.

    Returns:
        A validated :class:`LightCurve` instance.

    Raises:
        ValueError: If required columns are missing or fewer than 5 valid rows remain.
    """
    df = pd.read_csv(path)

    required_cols = {"time", "flux"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV at {path} is missing required columns: {sorted(missing)}")

    # Drop rows where time or flux is NaN/inf.
    df = df.replace([float("inf"), float("-inf")], float("nan"))
    df = df.dropna(subset=["time", "flux"])

    if len(df) < 5:
        raise ValueError(
            f"CSV at {path} has only {len(df)} valid rows after dropping NaN; "
            "at least 5 are required."
        )

    flux_err: list[float] | None = None
    if "flux_err" in df.columns:
        flux_err = df["flux_err"].astype(float).tolist()

    return LightCurve(
        source=source,  # type: ignore[arg-type]
        target_id=target_id,
        time=df["time"].astype(float).tolist(),
        flux=df["flux"].astype(float).tolist(),
        flux_err=flux_err,
        meta={"path": str(path)},
    )


def ensure_dir(path: Path) -> Path:
    """Create *path* (and all parents) if it does not already exist.

    Args:
        path: Directory path to create.

    Returns:
        The same *path* that was passed in, for convenient chaining.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(s: str, max_len: int = 180) -> str:
    """Convert an arbitrary string into a filesystem-safe filename fragment.

    Replaces any character that is not alphanumeric, ``-``, or ``_`` with
    an underscore, then truncates to *max_len* characters.

    Args:
        s: Input string (e.g. a candidate ID or target name).
        max_len: Maximum length of the returned string (default 180).

    Returns:
        A sanitised, possibly truncated string safe for use in file names.
    """
    sanitised = re.sub(r"[^A-Za-z0-9_\-]", "_", s)
    return sanitised[:max_len]
