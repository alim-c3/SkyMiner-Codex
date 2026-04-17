from __future__ import annotations

import logging
from typing import Any

from skyminer.config import SkyMinerConfig
from skyminer.models.schemas import Candidate, ValidationResult

log = logging.getLogger(__name__)


class CatalogValidator:
    """Validate candidates against known catalogs using astroquery where available.

    Design goals:
    - Mockable boundaries (network calls isolated in helper methods)
    - Conservative classification mapping
    - Never overclaim novelty based on absence of matches
    """

    def __init__(self, cfg: SkyMinerConfig) -> None:
        self.cfg = cfg

    def validate(self, candidate: Candidate) -> ValidationResult:
        if candidate.coord is None:
            return ValidationResult(status="unknown", details={"reason": "missing coordinates"})

        try:
            return self._validate_live(candidate)
        except ModuleNotFoundError:
            log.warning("astroquery not installed; validation disabled (returning unknown).")
            return ValidationResult(status="unknown", details={"reason": "astroquery missing"})
        except Exception as exc:
            log.exception("Catalog validation failed: %s", exc)
            return ValidationResult(status="unknown", details={"reason": "validation error", "error": str(exc)})

    def _validate_live(self, candidate: Candidate) -> ValidationResult:
        simbad = self._query_simbad(candidate)
        vizier = self._query_vizier(candidate)

        catalogs_checked: list[str] = []
        details: dict[str, Any] = {}
        status = "no_match"
        matched_name = None
        matched_type = None
        sep_arcsec = None

        if simbad is not None:
            catalogs_checked.append("SIMBAD")
            details["simbad"] = simbad
            if simbad.get("matched"):
                matched_name = simbad.get("main_id")
                matched_type = simbad.get("otype")
                sep_arcsec = simbad.get("separation_arcsec")
                status = _status_from_otype(matched_type)

        if vizier is not None:
            catalogs_checked.append("VizieR")
            details["vizier"] = vizier
            if vizier.get("matched") and status == "no_match":
                # VizieR matches without SIMBAD match: treat as unclear (could be cataloged in survey).
                status = "known_unclear"

        if not catalogs_checked:
            status = "unknown"

        return ValidationResult(
            status=status,  # type: ignore[arg-type]
            matched_name=matched_name,
            matched_type=matched_type,
            separation_arcsec=sep_arcsec,
            catalogs_checked=catalogs_checked,
            details=details,
        )

    # ---- Network-bound queries (mock these in tests) ----
    def _query_simbad(self, candidate: Candidate) -> dict[str, Any] | None:
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        from astroquery.simbad import Simbad

        coord = SkyCoord(candidate.coord.ra_deg * u.deg, candidate.coord.dec_deg * u.deg, frame="icrs")
        radius = float(self.cfg.validation.radius_arcsec) * u.arcsec

        custom = Simbad()
        custom.add_votable_fields("otype")

        res = custom.query_region(coord, radius=radius)
        if res is None or len(res) == 0:
            return {"matched": False}

        row = res[0]
        main_id = str(row["MAIN_ID"]).strip()
        otype = str(row["OTYPE"]).strip() if "OTYPE" in row.colnames else None
        return {
            "matched": True,
            "main_id": main_id,
            "otype": otype,
            # SIMBAD query_region doesn't directly provide separation; keep None for now.
            "separation_arcsec": None,
        }

    def _query_vizier(self, candidate: Candidate) -> dict[str, Any] | None:
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        from astroquery.vizier import Vizier

        coord = SkyCoord(candidate.coord.ra_deg * u.deg, candidate.coord.dec_deg * u.deg, frame="icrs")
        radius = float(self.cfg.validation.radius_arcsec) * u.arcsec

        viz = Vizier(columns=["*"], row_limit=5)
        tables = viz.query_region(coord, radius=radius, catalog=self.cfg.validation.vizier_catalogs)
        if not tables:
            return {"matched": False}

        # Keep a small summary to avoid bloating persistence.
        summary: list[dict[str, Any]] = []
        for tab in tables:
            for row in tab:
                summary.append({c: _safe_cell(row[c]) for c in tab.colnames[: min(12, len(tab.colnames))]})
        return {"matched": len(summary) > 0, "rows": summary[:10], "catalogs": list(self.cfg.validation.vizier_catalogs)}


def _safe_cell(v: Any) -> Any:
    try:
        if hasattr(v, "item"):
            return v.item()
    except Exception:
        pass
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", errors="replace")
    return v


def _status_from_otype(otype: str | None) -> str:
    if not otype:
        return "known_unclear"
    o = otype.lower()
    if "var" in o or "variable" in o:
        return "known_classified"
    # Many SIMBAD types are terse; treat unknown strings conservatively.
    return "known_unclear"


class VSXValidatorPlaceholder:
    """Placeholder for VSX (AAVSO) integration.

    TODO(VSX):
    - Decide on a stable, free access method (API/scrape) respecting AAVSO terms.
    - Implement query by coord with radius and parse variable-star type/period when available.
    - Add caching and provenance.
    """

    def validate(self, candidate: Candidate) -> ValidationResult:
        return ValidationResult(status="unknown", details={"reason": "vsx not implemented"})

