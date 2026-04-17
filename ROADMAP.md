# SkyMiner Roadmap

This roadmap tracks planned improvements beyond the MVP. SkyMiner is a **candidate discovery** tool; it will remain conservative in language and outputs.

## v0.2 (Next Version)

- Add a small offline dependency bundle and document `uv` install path.
- Make report generation accept real light curves (pass `LightCurve` objects through the pipeline and persist a minimal decimated series for reproducibility).
- Expand persistence schema:
  - store feature vectors per run
  - store validation summaries per run
  - store ranking outputs per run
- Add a caching/provenance layer for live ingestion:
  - cache TESS downloads with metadata
  - deterministic target selection for batch runs
- Improve validation logic:
  - compute angular separations
  - better SIMBAD object-type mapping
  - add VSX adapter (placeholder exists)
- Improve anomaly explainability:
  - top contributing features for z-score anomaly
  - standardized anomaly report fields
- Expand tests to run in CI with optional deps matrix (offline-only vs live extras).

## v0.3+

- Add multi-sector aggregation for TESS light curves.
- Add stronger novelty detection (cross-catalog evidence, historical baseline adapters).
- Add DASCH adapter (historical plate-series) once access + calibration plan is validated.
- Add “submission helper” scaffolding (still conservative; no claim automation).

