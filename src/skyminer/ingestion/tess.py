from __future__ import annotations

import logging
from typing import Any

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
        try:
            return self._ingest_with_lightkurve_tic(tic_ids)
        except ModuleNotFoundError:
            log.warning("lightkurve not installed; falling back to local sample ingestion.")
        except Exception as exc:
            log.exception("TESS ingestion failed; falling back to local sample. err=%s", exc)

        sample = self.cfg.paths.data_dir / "raw" / "sample_lightcurve.csv"
        return [read_csv_lightcurve(sample, target_id=f"LOCAL_FALLBACK_{tic}") for tic in tic_ids[:1]]

    def ingest_coordinates(self, coords_deg: list[tuple[float, float]]) -> list[LightCurve]:
        try:
            return self._ingest_with_lightkurve_coords(coords_deg)
        except ModuleNotFoundError:
            log.warning("lightkurve not installed; falling back to local sample ingestion.")
        except Exception as exc:
            log.exception("TESS coordinate ingestion failed; falling back to local sample. err=%s", exc)

        sample = self.cfg.paths.data_dir / "raw" / "sample_lightcurve.csv"
        return [read_csv_lightcurve(sample, target_id="LOCAL_FALLBACK_COORD")]

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

