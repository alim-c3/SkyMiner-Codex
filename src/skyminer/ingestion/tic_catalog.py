from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skyminer.config import SkyMinerConfig

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TicSampleResult:
    generated_at_utc: str
    seed: int
    requested_n: int
    returned_n: int
    tmag_max: float
    cone_radius_deg: float
    max_query_points: int
    tic_ids: list[str]


def _col_lookup(colnames: list[str], *candidates: str) -> str | None:
    lower = {c.lower(): c for c in colnames}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def sample_tic_ids_public(
    cfg: SkyMinerConfig,
    *,
    n: int,
    seed: int,
    tmag_max: float,
    cone_radius_deg: float,
    max_query_points: int,
) -> TicSampleResult:
    """Sample TIC IDs from the public TIC catalog via MAST.

    We use a deterministic RNG with `seed`. We generate random sky positions (RA uniform,
    Dec uniform in sin(dec) space) and query the TIC catalog around each point.

    This does not attempt to find "the best" variables; it produces a broad public sample
    so SkyMiner can score and rank interesting candidates.
    """

    if n <= 0:
        raise ValueError("n must be > 0")
    if max_query_points <= 0:
        raise ValueError("max_query_points must be > 0")
    if cone_radius_deg <= 0:
        raise ValueError("cone_radius_deg must be > 0")

    try:
        from astroquery.mast import Catalogs
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise ModuleNotFoundError("astroquery is required for TIC sampling (install extras: .[live]).") from exc

    rng = random.Random(int(seed))
    seen: set[str] = set()
    tic_ids: list[str] = []
    points_queried = 0

    while len(tic_ids) < n and points_queried < max_query_points:
        ra = rng.random() * 360.0
        u = rng.random() * 2.0 - 1.0  # uniform in [-1, 1]
        dec = math.degrees(math.asin(max(-1.0, min(1.0, u))))
        points_queried += 1

        # Catalogs.query_region accepts string coords; radius in deg.
        try:
            tab = Catalogs.query_region(f"{ra} {dec}", radius=float(cone_radius_deg), catalog="Tic")
        except Exception as exc:
            log.warning("TIC catalog query failed for ra=%s dec=%s: %s", ra, dec, exc)
            continue

        if tab is None or len(tab) == 0:
            continue

        colnames = list(getattr(tab, "colnames", []) or [])
        id_col = _col_lookup(colnames, "ID", "ticid", "TICID")
        tmag_col = _col_lookup(colnames, "Tmag", "tmag")

        if id_col is None:
            continue

        # Prefer bright sources; stable slice.
        rows: list[dict[str, Any]] = []
        for row in tab:
            try:
                tic = str(row[id_col]).strip()
                if not tic or not tic.isdigit():
                    continue
                tmag = None
                if tmag_col is not None:
                    try:
                        tmag = float(row[tmag_col])
                    except Exception:
                        tmag = None
                rows.append({"tic": tic, "tmag": tmag})
            except Exception:
                continue

        if not rows:
            continue

        def sort_key(r: dict[str, Any]) -> tuple[int, float]:
            # Prefer rows with a valid magnitude; then lower magnitude (brighter).
            mag = r.get("tmag")
            if mag is None or not isinstance(mag, (int, float)) or math.isnan(float(mag)):
                return (1, 99.0)
            return (0, float(mag))

        rows.sort(key=sort_key)
        for r in rows:
            if len(tic_ids) >= n:
                break
            tic = str(r["tic"])
            mag = r.get("tmag")
            if mag is not None:
                try:
                    if float(mag) > float(tmag_max):
                        continue
                except Exception:
                    pass
            if tic in seen:
                continue
            seen.add(tic)
            tic_ids.append(tic)

    return TicSampleResult(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        seed=int(seed),
        requested_n=int(n),
        returned_n=len(tic_ids),
        tmag_max=float(tmag_max),
        cone_radius_deg=float(cone_radius_deg),
        max_query_points=int(max_query_points),
        tic_ids=tic_ids,
    )


def load_or_create_tic_sample(
    cfg: SkyMinerConfig,
    *,
    n: int,
    seed: int,
    tmag_max: float,
    cone_radius_deg: float,
    max_query_points: int,
    cache_path: Path,
) -> TicSampleResult:
    """Load a cached TIC sample, or create and persist it."""

    try:
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            return TicSampleResult(**raw)
    except Exception:
        pass

    res = sample_tic_ids_public(
        cfg,
        n=n,
        seed=seed,
        tmag_max=tmag_max,
        cone_radius_deg=cone_radius_deg,
        max_query_points=max_query_points,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(res.__dict__, indent=2), encoding="utf-8")
    return res

