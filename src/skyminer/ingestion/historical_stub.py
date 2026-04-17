from __future__ import annotations

import logging

from skyminer.config import SkyMinerConfig
from skyminer.ingestion.base import BaseIngestor
from skyminer.models.schemas import LightCurve

log = logging.getLogger(__name__)


class HistoricalStubIngestor(BaseIngestor):
    """Stub adapter for historical datasets (e.g., DASCH).

    TODO(DASCH adapter):
    - Implement a DASCH plate-series ingestor that returns LightCurve objects.
    - Handle heterogeneous cadence, photometric calibration, and cross-era systematics.
    - Add caching and provenance metadata in LightCurve.meta.
    """

    def __init__(self, cfg: SkyMinerConfig) -> None:
        self.cfg = cfg

    def ingest_tic_ids(self, tic_ids: list[str]) -> list[LightCurve]:
        log.warning("HistoricalStubIngestor called for TIC IDs; returning empty. tic_ids=%s", tic_ids)
        return []

    def ingest_coordinates(self, coords_deg: list[tuple[float, float]]) -> list[LightCurve]:
        log.warning(
            "HistoricalStubIngestor called for coordinates; returning empty. coords=%s", coords_deg
        )
        return []

