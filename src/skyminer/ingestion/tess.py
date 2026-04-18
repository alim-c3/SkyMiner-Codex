from __future__ import annotations

import logging
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from skyminer.config import SkyMinerConfig
from skyminer.ingestion.base import BaseIngestor
from skyminer.models.schemas import LightCurve, SkyCoordLike
from skyminer.utils.io import read_csv_lightcurve

log = logging.getLogger(__name__)


class TessIngestor(BaseIngestor):
    """TESS ingestor using Lightkurve/MAST when available.

    Live mode requires optional dependency: `pip install -e ".[live]"`.
    If missing, ingestion gracefully falls back to local sample for smoke runs.
    """

    def __init__(self, cfg: SkyMinerConfig) -> None:
        self.cfg = cfg

    def ingest_tic_ids(self, tic_ids: list[str]) -> list[LightCurve]:
        mode = getattr(self.cfg.tess, "ingestion_mode", "spoc")

        def ingest_one(tic: str) -> list[LightCurve]:
            lcs: list[LightCurve] = []
            if mode in ("spoc", "spoc_then_tesscut"):
                try:
                    lcs = self._ingest_with_lightkurve_tic([tic])
                except ModuleNotFoundError:
                    log.warning("lightkurve not installed; cannot use SPOC ingestion.")
                except Exception as exc:
                    log.exception("SPOC ingestion failed for TIC %s: %s", tic, exc)
            if not lcs and mode in ("tesscut", "spoc_then_tesscut"):
                try:
                    lcs = self._ingest_with_tesscut_tic(tic)
                except ModuleNotFoundError:
                    log.warning("tesscut ingestion requires lightkurve+astroquery; returning empty.")
                except Exception as exc:
                    log.exception("tesscut ingestion failed for TIC %s: %s", tic, exc)
            return lcs

        out: list[LightCurve] = []
        max_workers = int(getattr(self.cfg.tess, "max_workers", 8))
        if len(tic_ids) <= 1 or max_workers <= 1:
            for tic in tic_ids:
                out.extend(ingest_one(tic))
            return out

        with ThreadPoolExecutor(max_workers=min(max_workers, len(tic_ids))) as ex:
            futs = [ex.submit(ingest_one, tic) for tic in tic_ids]
            for fut in as_completed(futs):
                try:
                    out.extend(fut.result())
                except Exception:
                    continue
        return out

    def ingest_coordinates(self, coords_deg: list[tuple[float, float]]) -> list[LightCurve]:
        mode = getattr(self.cfg.tess, "ingestion_mode", "spoc")

        def ingest_one_coord(ra: float, dec: float) -> list[LightCurve]:
            lcs: list[LightCurve] = []
            if mode in ("spoc", "spoc_then_tesscut"):
                try:
                    lcs = self._ingest_with_lightkurve_coords([(ra, dec)])
                except ModuleNotFoundError:
                    log.warning("lightkurve not installed; cannot use SPOC coordinate ingestion.")
                except Exception as exc:
                    log.exception("SPOC coordinate ingest failed ra=%s dec=%s: %s", ra, dec, exc)
            if not lcs and mode in ("tesscut", "spoc_then_tesscut"):
                try:
                    lcs = self._ingest_with_tesscut_coords([(ra, dec)])
                except ModuleNotFoundError:
                    log.warning("tesscut ingestion requires lightkurve; returning empty.")
                except Exception as exc:
                    log.exception("tesscut coordinate ingest failed ra=%s dec=%s: %s", ra, dec, exc)
            return lcs

        out: list[LightCurve] = []
        max_workers = int(getattr(self.cfg.tess, "max_workers", 8))
        if len(coords_deg) <= 1 or max_workers <= 1:
            for ra, dec in coords_deg:
                out.extend(ingest_one_coord(ra, dec))
        else:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(coords_deg))) as ex:
                futs = [ex.submit(ingest_one_coord, ra, dec) for ra, dec in coords_deg]
                for fut in as_completed(futs):
                    try:
                        out.extend(fut.result())
                    except Exception:
                        continue

        # Keep the old behavior for local smoke-like usage if nothing worked.
        if not out and mode == "spoc":
            sample = self.cfg.paths.data_dir / "raw" / "sample_lightcurve.csv"
            return [read_csv_lightcurve(sample, target_id="LOCAL_FALLBACK_COORD")]
        return out

    def _ingest_with_lightkurve_tic(self, tic_ids: list[str]) -> list[LightCurve]:
        import numpy as np
        import lightkurve as lk

        out: list[LightCurve] = []
        for tic in tic_ids:
            target = f"TIC {tic}"
            try:
                sr = lk.search_lightcurve(target, mission=self.cfg.tess.mission, author=self.cfg.tess.author)
                if len(sr) == 0:
                    log.warning("No TESS lightcurves found for %s", target)
                    continue
                lcfs = sr[: self.cfg.tess.max_lightcurves_per_target].download_all(
                    download_dir=str(self.cfg.tess.download_dir), quality_bitmask="default"
                )
                if lcfs is None:
                    log.warning("Download returned None for %s", target)
                    continue
                for lcf in lcfs:
                    lc = lcf.PDCSAP_FLUX
                    t = np.asarray(lc.time.value, dtype=float).tolist()
                    y = np.asarray(lc.flux.value, dtype=float).tolist()
                    e = None
                    if getattr(lc, "flux_err", None) is not None:
                        e = np.asarray(lc.flux_err.value, dtype=float).tolist()

                    meta: dict[str, Any] = {
                        "target": target,
                        "sector": getattr(lcf, "sector", None),
                        "camera": getattr(lcf, "camera", None),
                        "ccd": getattr(lcf, "ccd", None),
                        "author": self.cfg.tess.author,
                        "mission": self.cfg.tess.mission,
                        "time_format": str(getattr(lc.time, "format", "")),
                        "time_scale": str(getattr(lc.time, "scale", "")),
                    }

                    coord = None
                    try:
                        if getattr(lcf, "ra", None) is not None and getattr(lcf, "dec", None) is not None:
                            coord = SkyCoordLike(ra_deg=float(lcf.ra), dec_deg=float(lcf.dec))
                    except Exception:
                        coord = None

                    out.append(
                        LightCurve(
                            source="tess",
                            target_id=str(tic),
                            coord=coord,
                            time=t,
                            flux=y,
                            flux_err=e,
                            meta=meta,
                        )
                    )
            except Exception as exc:
                log.exception("Failed TESS ingest for %s: %s", target, exc)
                continue
        return out

    def _ingest_with_lightkurve_coords(self, coords_deg: list[tuple[float, float]]) -> list[LightCurve]:
        import numpy as np
        import lightkurve as lk
        from astropy.coordinates import SkyCoord
        import astropy.units as u

        out: list[LightCurve] = []
        for ra, dec in coords_deg:
            coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
            try:
                sr = lk.search_lightcurve(coord, mission=self.cfg.tess.mission, author=self.cfg.tess.author)
                if len(sr) == 0:
                    log.warning("No TESS lightcurves found for coord ra=%s dec=%s", ra, dec)
                    continue
                lcfs = sr[: self.cfg.tess.max_lightcurves_per_target].download_all(
                    download_dir=str(self.cfg.tess.download_dir), quality_bitmask="default"
                )
                if lcfs is None:
                    continue
                for lcf in lcfs:
                    lc = lcf.PDCSAP_FLUX
                    t = np.asarray(lc.time.value, dtype=float).tolist()
                    y = np.asarray(lc.flux.value, dtype=float).tolist()
                    e = None
                    if getattr(lc, "flux_err", None) is not None:
                        e = np.asarray(lc.flux_err.value, dtype=float).tolist()
                    out.append(
                        LightCurve(
                            source="tess",
                            target_id=f"coord_{ra:.5f}_{dec:.5f}",
                            coord=SkyCoordLike(ra_deg=float(ra), dec_deg=float(dec)),
                            time=t,
                            flux=y,
                            flux_err=e,
                            meta={"author": self.cfg.tess.author, "mission": self.cfg.tess.mission},
                        )
                    )
            except Exception as exc:
                log.exception("Failed coordinate ingest ra=%s dec=%s: %s", ra, dec, exc)
        return out

    def _resolve_tic_to_coord(self, tic: str) -> SkyCoordLike | None:
        # TIC coordinate lookup (public TIC catalog via MAST).
        from astroquery.mast import Catalogs

        tab = Catalogs.query_object(f"TIC {tic}", catalog="Tic")
        if tab is None or len(tab) == 0:
            return None
        colnames = list(getattr(tab, "colnames", []) or [])
        lower = {c.lower(): c for c in colnames}
        ra_col = lower.get("ra") or lower.get("ra_icrs")
        dec_col = lower.get("dec") or lower.get("dec_icrs")
        if not ra_col or not dec_col:
            return None
        row = tab[0]
        try:
            return SkyCoordLike(ra_deg=float(row[ra_col]), dec_deg=float(row[dec_col]))
        except Exception:
            return None

    def _ingest_with_tesscut_tic(self, tic: str) -> list[LightCurve]:
        coord = self._resolve_tic_to_coord(tic)
        if coord is None:
            log.warning("Could not resolve TIC %s to coordinates for tesscut.", tic)
            return []
        lcs = self._ingest_with_tesscut_coords([(coord.ra_deg, coord.dec_deg)])
        # Ensure target_id remains the TIC for downstream consistency.
        for lc in lcs:
            lc.target_id = str(tic)
            lc.meta["tic_id"] = str(tic)
        return lcs

    def _ingest_with_tesscut_coords(self, coords_deg: list[tuple[float, float]]) -> list[LightCurve]:
        import numpy as np
        import lightkurve as lk
        from astropy.coordinates import SkyCoord
        import astropy.units as u

        out: list[LightCurve] = []
        cutout_size = int(getattr(self.cfg.tess, "tesscut_cutout_size", 10))
        thresh = float(getattr(self.cfg.tess, "tesscut_threshold_sigma", 3.0))
        qmask = str(getattr(self.cfg.tess, "tesscut_quality_bitmask", "default"))

        for ra, dec in coords_deg:
            coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
            try:
                sr = lk.search_tesscut(coord)
                if len(sr) == 0:
                    log.warning("No TESSCut data found for coord ra=%s dec=%s", ra, dec)
                    continue
                tpfs = sr[: self.cfg.tess.max_lightcurves_per_target].download_all(cutout_size=cutout_size)
                if tpfs is None:
                    continue
                for tpf in tpfs:
                    try:
                        mask = tpf.create_threshold_mask(threshold=thresh)
                        lc = tpf.to_lightcurve(aperture_mask=mask, quality_bitmask=qmask)
                        t = np.asarray(lc.time.value, dtype=float).tolist()
                        y = np.asarray(lc.flux.value, dtype=float).tolist()
                        e = None
                        if getattr(lc, "flux_err", None) is not None:
                            e = np.asarray(lc.flux_err.value, dtype=float).tolist()
                        meta: dict[str, Any] = {
                            "method": "tesscut",
                            "cutout_size": cutout_size,
                            "threshold_sigma": thresh,
                            "quality_bitmask": qmask,
                            "sector": getattr(tpf, "sector", None),
                            "author": "tesscut",
                            "mission": self.cfg.tess.mission,
                        }
                        out.append(
                            LightCurve(
                                source="tess",
                                target_id=f"coord_{ra:.5f}_{dec:.5f}",
                                coord=SkyCoordLike(ra_deg=float(ra), dec_deg=float(dec)),
                                time=t,
                                flux=y,
                                flux_err=e,
                                meta=meta,
                            )
                        )
                    except Exception as exc:
                        log.exception("tesscut photometry failed ra=%s dec=%s: %s", ra, dec, exc)
            except Exception as exc:
                log.exception("Failed tesscut search/download ra=%s dec=%s: %s", ra, dec, exc)
        return out
