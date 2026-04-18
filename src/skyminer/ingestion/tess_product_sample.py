from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from skyminer.config import SkyMinerConfig

log = logging.getLogger(__name__)

_TIC_RE = re.compile(r"\bTIC\s*([0-9]+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TessProductSampleResult:
    generated_at_utc: str
    seed: int
    requested_n: int
    returned_n: int
    max_queries: int
    tic_ids: list[str]


def _extract_tics_from_search_table(table) -> list[str]:  # type: ignore[no-untyped-def]
    try:
        colnames = list(getattr(table, "colnames", []) or [])
    except Exception:
        colnames = []
    lower = {c.lower(): c for c in colnames}
    tcol = lower.get("target_name") or lower.get("targetname") or lower.get("target")
    if not tcol:
        return []
    out: list[str] = []
    try:
        for row in table:
            m = _TIC_RE.search(str(row[tcol]) or "")
            if m:
                out.append(m.group(1))
    except Exception:
        return []
    return out


def sample_tess_spoc_product_tic_ids(
    cfg: SkyMinerConfig,
    *,
    n: int,
    seed: int,
    max_queries: int = 2000,
) -> TessProductSampleResult:
    """Sample TIC IDs that appear to have existing SPOC light curve products.

    Strategy:
    - Query lightkurve search at random sky positions.
    - Extract TIC IDs from the returned search table (target_name).

    This avoids massive full-table MAST queries and tends to find ingestible targets quickly.
    """

    if n <= 0:
        raise ValueError("n must be > 0")
    if max_queries <= 0:
        raise ValueError("max_queries must be > 0")

    import lightkurve as lk
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    rng = random.Random(int(seed))
    seen: set[str] = set()
    tic_ids: list[str] = []
    queries = 0

    while len(tic_ids) < n and queries < max_queries:
        ra = rng.random() * 360.0
        dec = rng.uniform(-80.0, 80.0)  # avoid extreme poles to reduce resolver edge cases
        queries += 1

        try:
            sr = lk.search_lightcurve(
                SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs"),
                mission=cfg.tess.mission,
                author=cfg.tess.author,
            )
        except Exception:
            continue

        if len(sr) == 0:
            continue

        try:
            tics = _extract_tics_from_search_table(sr.table)
        except Exception:
            tics = []
        if not tics:
            continue
        for tic in tics:
            if len(tic_ids) >= n:
                break
            if tic in seen:
                continue
            seen.add(tic)
            tic_ids.append(tic)

    return TessProductSampleResult(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        seed=int(seed),
        requested_n=int(n),
        returned_n=len(tic_ids),
        max_queries=int(max_queries),
        tic_ids=tic_ids,
    )


def load_or_create_tess_product_sample(
    cfg: SkyMinerConfig,
    *,
    n: int,
    seed: int,
    max_queries: int,
    cache_path: Path,
) -> TessProductSampleResult:
    try:
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            return TessProductSampleResult(**raw)
    except Exception:
        pass

    res = sample_tess_spoc_product_tic_ids(cfg, n=n, seed=seed, max_queries=max_queries)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(res.__dict__, indent=2), encoding="utf-8")
    return res

