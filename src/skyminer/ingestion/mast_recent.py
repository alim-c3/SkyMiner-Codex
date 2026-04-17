from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from skyminer.config import SkyMinerConfig

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecentMASTResult:
    """Result of a recent-MAST scan.

    Note: "last night" is operationalized as "the last N hours (UTC)" because
    MAST/TESS does not provide a clean 'nightly batch' concept for all products.
    """

    window_start_utc: datetime
    window_end_utc: datetime
    products_matched: int
    tic_ids: list[str]


_TIC_RE = re.compile(r"\bTIC\s*([0-9]+)\b", re.IGNORECASE)


def fetch_recent_tic_ids(
    cfg: SkyMinerConfig,
    *,
    hours: int = 24,
    max_tics: int = 500,
    _now_utc: callable[[], datetime] | None = None,
    _Observations: object | None = None,
    _Time: object | None = None,
) -> RecentMASTResult:
    """Fetch TIC IDs with TESS time-series products seen by MAST in the last `hours`.

    Implementation note:
    We query MAST Observations for TESS `dataproduct_type='timeseries'` and filter by
    `t_obs_release` if available, else fall back to `t_min` (observation start time).
    """

    if hours <= 0:
        raise ValueError("hours must be > 0")
    if max_tics <= 0:
        raise ValueError("max_tics must be > 0")

    now_fn = _now_utc or (lambda: datetime.now(timezone.utc))
    window_end = now_fn()
    window_start = window_end - timedelta(hours=int(hours))

    if _Time is None:
        from astropy.time import Time as _AstropyTime  # type: ignore

        _Time = _AstropyTime
    if _Observations is None:
        from astroquery.mast import Observations as _MASTObservations  # type: ignore

        _Observations = _MASTObservations

    start_mjd = float(_Time(window_start).mjd)  # type: ignore[misc]
    end_mjd = float(_Time(window_end).mjd)  # type: ignore[misc]

    # Try for "recently released" first. If MAST doesn't support that field, fall back.
    query_fields_tried: list[str] = []
    obs = None
    try:
        query_fields_tried.append("t_obs_release")
        obs = _Observations.query_criteria(  # type: ignore[no-any-return,attr-defined]
            obs_collection="TESS",
            dataproduct_type="timeseries",
            t_obs_release=[start_mjd, end_mjd],
        )
    except Exception:
        obs = None

    if obs is None or (hasattr(obs, "__len__") and len(obs) == 0):
        query_fields_tried.append("t_min")
        obs = _Observations.query_criteria(  # type: ignore[no-any-return,attr-defined]
            obs_collection="TESS",
            dataproduct_type="timeseries",
            t_min=[start_mjd, end_mjd],
        )

    products_matched = int(len(obs)) if obs is not None else 0
    if obs is None or products_matched == 0:
        log.warning(
            "No MAST products matched for recent window (hours=%s). fields_tried=%s",
            hours,
            query_fields_tried,
        )
        return RecentMASTResult(
            window_start_utc=window_start,
            window_end_utc=window_end,
            products_matched=0,
            tic_ids=[],
        )

    tic_ids: list[str] = []
    seen: set[str] = set()

    # Most reliable field is target_name (often "TIC 123..."), but we keep fallbacks.
    cols = set(getattr(obs, "colnames", []) or [])
    target_col = "target_name" if "target_name" in cols else None
    obsid_col = "obs_id" if "obs_id" in cols else None

    def add_from_text(txt: str) -> None:
        m = _TIC_RE.search(txt or "")
        if not m:
            return
        tic = m.group(1)
        if tic in seen:
            return
        seen.add(tic)
        tic_ids.append(tic)

    for row in obs:
        if target_col is not None:
            try:
                add_from_text(str(row[target_col]))
            except Exception:
                pass
        if len(tic_ids) >= max_tics:
            break
        if obsid_col is not None:
            try:
                add_from_text(str(row[obsid_col]))
            except Exception:
                pass
        if len(tic_ids) >= max_tics:
            break

    if not tic_ids:
        log.warning(
            "Recent MAST query returned %s products but no TIC IDs could be parsed. cols=%s",
            products_matched,
            sorted(list(cols))[:20],
        )

    return RecentMASTResult(
        window_start_utc=window_start,
        window_end_utc=window_end,
        products_matched=products_matched,
        tic_ids=tic_ids,
    )
