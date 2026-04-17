from __future__ import annotations

import abc
from typing import Protocol

from skyminer.models.schemas import LightCurve


class BaseIngestor(abc.ABC):
    """Abstract base ingestor.

    Ingestors return canonical `LightCurve` objects. They MUST be resilient:
    ingestion failures should be logged and skipped, not crash a batch run.
    """

    @abc.abstractmethod
    def ingest_tic_ids(self, tic_ids: list[str]) -> list[LightCurve]:
        raise NotImplementedError

    @abc.abstractmethod
    def ingest_coordinates(self, coords_deg: list[tuple[float, float]]) -> list[LightCurve]:
        raise NotImplementedError


class SupportsLogging(Protocol):
    def info(self, msg: str, *args: object, **kwargs: object) -> None: ...
    def warning(self, msg: str, *args: object, **kwargs: object) -> None: ...
    def exception(self, msg: str, *args: object, **kwargs: object) -> None: ...

