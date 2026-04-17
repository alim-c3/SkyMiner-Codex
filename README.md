# SkyMiner

SkyMiner is a modular Python pipeline for candidate variable star and stellar anomaly discovery using public astronomy data, primarily TESS light curves retrieved via the MAST archive and the Lightkurve library. It ingests time-series photometry, extracts robust statistical and frequency-domain features, scores each target for anomalousness and periodicity, cross-checks results against public catalogs (SIMBAD, VizieR/Gaia DR3), and generates human-readable candidate reports. SkyMiner is **not** a confirmed discovery tool — every output is a candidate that requires independent human follow-up before any scientific claim can be made.

---

## Scientific Purpose

Automated light curve analysis matters because public sky surveys now produce photometry for tens of millions of stars per sector, far exceeding the capacity for manual inspection. Within these data there exist populations of objects that are poorly characterized or entirely unclassified: eclipsing binaries with atypical depth ratios, pulsating stars near the instability strip, flare stars with sparse archival coverage, and periodic variables that fall outside the standard classification bins. SkyMiner provides a reproducible, auditable pipeline to prioritize which targets are most worth a human expert's attention, using only interpretable statistical methods (z-score anomaly detection, Lomb-Scargle periodograms, IsolationForest) and public catalog cross-checks.

Kinds of objects the pipeline may surface:
- Eclipsing binary candidates (periodic dips, near-symmetric light curves)
- Pulsating star candidates (stable sinusoidal or multi-harmonic periodicity)
- Flare star candidates (strong positive outliers, high skew, non-periodic)
- Unclassified periodic variables (significant Lomb-Scargle power, no catalog match)

---

## Architecture Overview

SkyMiner is organized as a linear pipeline of modular, independently testable stages. Each stage receives well-typed Pydantic objects and returns well-typed Pydantic objects. All network-dependent adapters implement a common abstract interface (`BaseIngestor`) so they can be swapped or mocked without modifying the core pipeline.

**Pipeline stages:**

1. **Ingest** — `BaseIngestor` subclasses fetch or load light curves and return a list of `LightCurve` objects. Currently implemented: `TessIngestor` (live MAST via lightkurve, or offline CSV fallback) and `HistoricalStubIngestor` (placeholder for future DASCH adapter).
2. **Persist Target** — Each ingested target is upserted to the SQLite `targets` table, enabling idempotent re-runs.
3. **Clean** — `clean_lightcurve()` removes NaN/inf values, sorts by time, and optionally applies Savitzky-Golay smoothing. Raises if fewer than 5 finite points remain.
4. **Normalize** — `normalize_lightcurve()` applies z-score, robust z-score, or no normalization to the flux array.
5. **Extract Features** — `extract_features()` computes 17 contractual features (statistics, autocorrelation at four lags, peak/trough counts, Lomb-Scargle dominant period and power).
6. **Estimate Periodicity** — `estimate_periodicity()` runs the Lomb-Scargle periodogram and returns a `PeriodicityResult` with a heuristic quality score.
7. **Build Candidates** — A `Candidate` object is constructed per target, holding features and periodicity results.
8. **Detect Anomalies** — `compute_anomaly()` operates in batch across all candidates in a pipeline run, computing z-score flags and (when batch size >= 8) IsolationForest scores.
9. **Score** — `score_candidate()` combines anomaly, periodicity, variability, and novelty sub-scores into a weighted total score in [0, 1].
10. **Validate** — `CatalogValidator` cross-checks each candidate's sky coordinates against SIMBAD and VizieR/Gaia DR3 within a configurable search radius, labeling each as `known_classified`, `known_unclear`, `no_match`, or `unknown`.
11. **Persist Candidates** — Scored, validated candidates are upserted to the SQLite `candidates` table.
12. **Report** — `generate_reports()` writes per-candidate JSON, Markdown, light curve PNG, and periodogram PNG artifacts for the top-k candidates.
13. **Return Summary** — `run_pipeline()` returns a summary dict: `{run_id, mode, targets_ingested, candidates_scored, outputs_dir, db_path}`.

---

## Installation

Python 3.11 or newer is required.

**Local / offline mode** (no network calls, uses bundled sample data):
```bash
pip install -e .
```

**Live mode** (TESS light curve downloads via MAST + catalog queries via astroquery):
```bash
pip install -e ".[live]"
```

**Development mode** (includes pytest, coverage, and mocking libraries):
```bash
pip install -e ".[live,dev]"
```

---

## Setup

After installing, copy the example environment file and create the output directory tree:

```bash
cp .env.example .env
# Edit .env to override any defaults (optional)
```

Or use the Makefile shortcut, which does both steps automatically:

```bash
make setup
```

The `outputs/` directory structure will be:
```
outputs/
  reports/      # Markdown + JSON per candidate
  plots/        # Light curve and periodogram PNGs
  candidates/   # Ranked candidate lists
  logs/         # Pipeline run logs
```

---

## Running the Pipeline

**Offline smoke test** (no network, validates the install):
```bash
make smoke-test
# or equivalently:
skyminer smoke-test
# or:
python -m skyminer.cli smoke-test
```

**Live mode by TIC ID:**
```bash
skyminer run-pipeline --mode live --tic 25155310
```

**Live mode by sky coordinates (RA/Dec in degrees):**
```bash
skyminer run-pipeline --mode live --ra 83.82 --dec -5.39
```

**Full pipeline via Python module:**
```bash
python -m skyminer.cli run-pipeline --mode local
```

**All Makefile targets:**

| Target | Description |
|---|---|
| `make setup` | Create output directories; copy `.env.example` to `.env` if not present |
| `make install` | Install core dependencies (`pip install -e .`) |
| `make install-live` | Install with live data extras (`pip install -e ".[live]"`) |
| `make install-dev` | Install with live + dev extras (`pip install -e ".[live,dev]"`) |
| `make smoke-test` | Run offline smoke test using bundled sample data |
| `make run` | Run the full pipeline in local mode |
| `make test` | Run the test suite with pytest |
| `make test-cov` | Run tests with coverage report |
| `make lint` | Lint source code (ruff if available, else flake8) |
| `make clean` | Remove caches, build artifacts, and outputs |
| `make help` | Print all available Makefile targets |

---

## Output Organization

All pipeline artifacts are written under the `outputs/` directory (configurable via `config/default.yaml` or `SKYMINER_OUTPUTS_DIR` env var):

```
outputs/
  reports/
    {candidate_id}.json          # Full candidate data as JSON
    {candidate_id}.md            # Human-readable Markdown report with scientific caveats
  plots/
    {candidate_id}_lightcurve.png    # Cleaned, normalized light curve plot
    {candidate_id}_periodogram.png   # Lomb-Scargle periodogram (if periodicity detected)
  candidates/
    run_{run_id}_top_candidates.json # Ranked list of top-k candidates for the run
  logs/
    skyminer.log                 # Rotating pipeline log
  skyminer.sqlite                # SQLite database of all runs and candidates
```

---

## How to Add a New Data Adapter

SkyMiner's ingestion layer is adapter-based. All adapters implement `BaseIngestor` from `src/skyminer/ingestion/base.py`. To add a new source (for example, DASCH digitized photographic plates):

1. **Subclass `BaseIngestor`** in a new file, e.g. `src/skyminer/ingestion/dasch.py`.

2. **Implement `ingest_tic_ids()`** — given a list of TIC ID strings, return a list of `LightCurve` objects. If TIC IDs are not applicable to your source, log a warning and return `[]`.

3. **Implement `ingest_coordinates()`** — given a list of `(ra_deg, dec_deg)` tuples, query your source and return a list of `LightCurve` objects with `source` set to your adapter's source label.

4. **Set the `source` field** on every returned `LightCurve` to a string literal matching one of the values accepted by the schema (`"tess"`, `"historical_stub"`, or add a new `Literal` value to `schemas.py` and `IngestTarget`).

5. **Register the adapter** in `src/skyminer/pipeline/runner.py` — add a branch in the ingestor selection logic (typically a dict keyed by mode or source name).

6. **Reference the stub** at `src/skyminer/ingestion/historical_stub.py` as the minimal working template. The stub intentionally returns `[]` with a WARNING log, which is the correct behavior when a source is not yet implemented.

> Note: The DASCH adapter is a planned future addition. The `HistoricalStubIngestor` and the `source="historical_stub"` literal in the schema are already present to avoid any future migration.

---

## Limitations

- **Network dependency for live mode:** MAST, SIMBAD, and VizieR can be unavailable or slow. SkyMiner logs failures per-target and continues the run, but a fully offline result set may be incomplete.
- **TESS sky coverage:** TESS covers the sky in sectors of ~27 days. Not all targets have available light curves, especially in the continuous viewing zones vs. single-sector fields.
- **No deep learning:** SkyMiner uses only classical statistical methods (Lomb-Scargle, z-score, IsolationForest). This is by design for interpretability and auditability, but deep-learning-based classifiers would likely improve recall for subtle variability types.
- **Batch-scoped anomaly scoring:** IsolationForest anomaly scores are computed relative to the current pipeline batch. A target that would score as anomalous in a larger population may not be flagged in a small batch (fewer than 8 targets automatically falls back to z-score only).
- **Coordinate uncertainty:** Catalog cross-checks use a fixed search radius (default 5 arcsec). Targets with significant proper motion or astrometric uncertainty may be mis-matched or missed.

---

## Scientific Caution

**SkyMiner surfaces CANDIDATES only.**

No output from SkyMiner should be interpreted as a confirmed astronomical discovery. The pipeline is a prioritization tool that helps human experts decide which targets warrant follow-up observation. Systematic false positives are expected, especially from instrumental artifacts, contaminated pixels, and background eclipsing binaries.

All candidates require independent human validation before any scientific claim is made. Recommended follow-up steps include:
- Cross-checking with the full SIMBAD/VizieR/VSX/ASAS-SN catalogs manually
- Inspecting the pixel-level TESS Full Frame Images for contamination
- Multi-epoch photometric monitoring with an independent instrument
- Ideally: follow-up spectroscopy to confirm variability type and rule out instrumental or environmental causes

The Markdown reports generated by SkyMiner include a mandatory scientific caveats section that repeats this warning.

---

## Contributing

Contributions are welcome. Before submitting a pull request, ensure all tests pass:

```bash
make test
```

For coverage reporting:
```bash
make test-cov
```

Please follow the existing module structure and keep all Pydantic schemas consistent with `ARCHITECTURE_CONTRACTS.md`, which is the single source of truth for interfaces and schema definitions.
