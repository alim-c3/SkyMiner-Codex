"""SkyMiner Pydantic v2 schemas — single source of truth for all data contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SkyCoordLike(BaseModel):
    """Minimal coordinate representation (ICRS degrees)."""

    ra_deg: float
    dec_deg: float


class LightCurve(BaseModel):
    """Canonical internal light-curve representation.

    ``time`` is in days (BTJD for TESS).  ``flux`` is relative flux (unitless).
    """

    source: Literal["tess", "local_sample", "historical_stub"]
    target_id: str
    coord: Optional[SkyCoordLike] = None

    time: list[float]
    flux: list[float]
    flux_err: Optional[list[float]] = None

    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("time", "flux")
    @classmethod
    def _min_length(cls, v: list[float]) -> list[float]:
        if len(v) < 5:
            raise ValueError("time and flux must each have at least 5 elements.")
        return v

    def as_arrays(self) -> tuple:
        """Return (t, y, e) as numpy arrays.  ``e`` is None when flux_err is absent."""
        import numpy as np  # deferred so numpy is optional at import time

        t = np.asarray(self.time, dtype=float)
        y = np.asarray(self.flux, dtype=float)
        e = None if self.flux_err is None else np.asarray(self.flux_err, dtype=float)
        return t, y, e


class IngestTarget(BaseModel):
    """Describes a single object to be ingested.

    At least one of ``tic_id`` or the coordinate pair (``ra_deg`` + ``dec_deg``) must
    be supplied.
    """

    tic_id: Optional[str] = None
    ra_deg: Optional[float] = None
    dec_deg: Optional[float] = None
    source: Literal["tess", "historical_stub"] = "tess"

    @model_validator(mode="after")
    def _require_identifier(self) -> IngestTarget:
        has_tic = self.tic_id is not None
        has_coords = self.ra_deg is not None and self.dec_deg is not None
        if not has_tic and not has_coords:
            raise ValueError(
                "IngestTarget requires at least one of: tic_id, or both ra_deg and dec_deg."
            )
        return self


class PeriodicityResult(BaseModel):
    """Output of the periodicity-estimation step."""

    dominant_period_days: Optional[float] = None
    power: Optional[float] = None
    quality: float = 0.0  # heuristic [0, 1]; tanh(max(0, power))
    method: str = "lomb_scargle"
    notes: Optional[str] = None


class CandidateScoreBreakdown(BaseModel):
    """Weighted score components for a single candidate."""

    anomaly: float      # [0, 1]
    periodicity: float  # [0, 1]
    variability: float  # [0, 1]
    novelty: float      # [0, 1]
    total: float        # weighted sum, clipped [0, 1]


class ValidationResult(BaseModel):
    """Result of cross-matching a candidate against external catalogs."""

    status: Literal["known_classified", "known_unclear", "no_match", "unknown"] = "unknown"
    matched_name: Optional[str] = None
    matched_type: Optional[str] = None
    separation_arcsec: Optional[float] = None
    catalogs_checked: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Candidate(BaseModel):
    """A single candidate object assembled from ingestion through scoring.

    ``candidate_id`` must follow the format ``"{source}:{target_id}"``.
    """

    candidate_id: str
    target_id: str
    source: str
    coord: Optional[SkyCoordLike] = None

    features: dict[str, float] = Field(default_factory=dict)
    periodicity: PeriodicityResult = Field(default_factory=PeriodicityResult)
    anomaly: dict[str, Any] = Field(default_factory=dict)
    validation: ValidationResult = Field(default_factory=ValidationResult)

    score: Optional[CandidateScoreBreakdown] = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id_format(cls, v: str) -> str:
        if ":" not in v:
            raise ValueError(
                f"candidate_id must follow the format '{{source}}:{{target_id}}', got: {v!r}"
            )
        return v

    @classmethod
    def build_id(cls, source: str, target_id: str) -> str:
        """Construct a canonical candidate_id from source and target_id."""
        return f"{source}:{target_id}"


class PipelineRun(BaseModel):
    """Metadata record for a single end-to-end pipeline execution."""

    run_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: Literal["local", "live"] = "local"
    config_path: str
    params: dict[str, Any] = Field(default_factory=dict)
