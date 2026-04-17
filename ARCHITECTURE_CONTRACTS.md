# SkyMiner — Architecture Contracts

**Version:** 1.0  
**Date:** 2026-04-17  
**Status:** Source of truth for all coding agents

This document defines exact interfaces, schemas, config keys, and design decisions for the SkyMiner pipeline. Coding agents must not deviate from these contracts without updating this document first.

---

## 1. Pydantic Schemas

All schemas live in `src/skyminer/models/schemas.py` and use Pydantic v2 (`BaseModel`).

### 1.1 `SkyCoordLike`

```python
class SkyCoordLike(BaseModel):
    ra_deg: float
    dec_deg: float
```

### 1.2 `LightCurve`

```python
class LightCurve(BaseModel):
    source:    Literal["tess", "local_sample", "historical_stub"]
    target_id: str
    coord:     Optional[SkyCoordLike]
    time:      list[float]    # days (BTJD for TESS)
    flux:      list[float]    # relative flux (unitless)
    flux_err:  Optional[list[float]]
    meta:      dict[str, Any]  # default {}
```

Validator: `time` and `flux` must each have at least 5 elements.
Helper: `as_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray | None]`

### 1.3 `IngestTarget`

```python
class IngestTarget(BaseModel):
    tic_id:  Optional[str]
    ra_deg:  Optional[float]
    dec_deg: Optional[float]
    source:  Literal["tess", "historical_stub"] = "tess"
```

Constraint: at least one of `tic_id` or (`ra_deg` AND `dec_deg`) must be provided.

### 1.4 `ExtractedFeatures` — Contractual Keys

| Key | Notes |
|-----|-------|
| `n_points` | Count of data points |
| `mean` | Arithmetic mean of flux |
| `median` | Median flux |
| `std` | Standard deviation |
| `var` | Variance |
| `mad` | Median absolute deviation |
| `amplitude_p95_p5` | 95th percentile minus 5th percentile |
| `skew` | Fisher skewness; 0.0 if n < 8 |
| `kurtosis` | Fisher excess kurtosis; 0.0 if n < 8 |
| `autocorr_lag_1` | Normalized autocorrelation at lag 1 |
| `autocorr_lag_2` | Normalized autocorrelation at lag 2 |
| `autocorr_lag_5` | Normalized autocorrelation at lag 5 |
| `autocorr_lag_10` | Normalized autocorrelation at lag 10 |
| `n_peaks` | Peak count above `features.peak_prominence` threshold |
| `n_troughs` | Trough count above `features.peak_prominence` threshold |
| `ls_dominant_period_days` | Best-fit Lomb-Scargle period; NaN if unavailable |
| `ls_max_power` | Power at dominant period; NaN if unavailable |

Non-`ls_` keys are guaranteed finite (NaN → 0.0). `ls_` keys may be NaN.

### 1.5 `PeriodicityResult`

```python
class PeriodicityResult(BaseModel):
    dominant_period_days: Optional[float]
    power:                Optional[float]
    quality:              float = 0.0      # heuristic [0,1]; tanh(max(0,power))
    method:               str   = "lomb_scargle"
    notes:                Optional[str]
```

### 1.6 `AnomalyResult` — Contractual Keys

| Key | Type | Always present? |
|-----|------|----------------|
| `zscore_threshold` | float | Yes |
| `zscore_mean_abs` | float | Yes |
| `zscore_score` | float | Yes — clipped [0,10] |
| `zscore_flagged_features` | dict[str, bool] | Yes |
| `isolation_forest_score` | float | No — present when IF enabled and n >= 8 |
| `isolation_forest_label` | int | No — present with IF score |

### 1.7 `CandidateScoreBreakdown`

```python
class CandidateScoreBreakdown(BaseModel):
    anomaly:     float  # [0,1]
    periodicity: float  # [0,1]
    variability: float  # [0,1]
    novelty:     float  # [0,1]
    total:       float  # weighted sum, clipped [0,1]
```

Novelty from ValidationResult.status: `no_match` → 1.0, `known_unclear` → 0.5, `known_classified` → 0.0, `unknown` → 0.2

### 1.8 `Candidate`

```python
class Candidate(BaseModel):
    candidate_id: str
    target_id:    str
    source:       str
    coord:        Optional[SkyCoordLike]
    features:     dict[str, float]              # default {}
    periodicity:  PeriodicityResult
    anomaly:      dict[str, Any]                # default {}
    validation:   ValidationResult
    score:        Optional[CandidateScoreBreakdown]
    notes:        list[str]                     # default []
```

`candidate_id` format: `"{source}:{target_id}"`

### 1.9 `ValidationResult`

```python
class ValidationResult(BaseModel):
    status:            Literal["known_classified", "known_unclear", "no_match", "unknown"] = "unknown"
    matched_name:      Optional[str]
    matched_type:      Optional[str]
    separation_arcsec: Optional[float]
    catalogs_checked:  list[str]   # default []
    details:           dict[str, Any]  # default {}
```

SIMBAD OTYPE → status: `"var"` or `"variable"` in otype → `"known_classified"`; other non-empty otype → `"known_unclear"`.

### 1.10 `PipelineRun`

```python
class PipelineRun(BaseModel):
    run_id:      str
    started_at:  datetime
    mode:        Literal["local", "live"] = "local"
    config_path: str
    params:      dict[str, Any]  # default {}
```

---

## 2. Module Interfaces

### 2.1 `ingestion/base.py`

```python
class BaseIngestor(abc.ABC):
    @abc.abstractmethod
    def ingest_tic_ids(self, tic_ids: list[str]) -> list[LightCurve]: ...
    @abc.abstractmethod
    def ingest_coordinates(self, coords_deg: list[tuple[float, float]]) -> list[LightCurve]: ...
```

Contract: catch per-target exceptions, log them, never raise to caller.

### 2.2 `ingestion/tess.py` — `TessIngestor`

- Config keys: `tess.mission`, `tess.author`, `tess.max_lightcurves_per_target`, `tess.download_dir`, `paths.data_dir`
- Falls back to `data/raw/sample_lightcurve.csv` when lightkurve absent
- `source="tess"` on returned objects

### 2.3 `ingestion/historical_stub.py` — `HistoricalStubIngestor`

- Both methods log WARNING and return `[]`
- Placeholder for future DASCH adapter

### 2.4 `preprocessing/cleaning.py` — `clean_lightcurve(lc, cfg) -> LightCurve`

Steps: remove NaN/inf, sort by time, optional Savitzky-Golay smoothing.  
Raises `ValueError` if fewer than 5 finite points remain.  
Config: `preprocessing.smoothing.{enabled,method,window_length,polyorder}`

### 2.5 `preprocessing/normalization.py` — `normalize_lightcurve(lc, cfg) -> LightCurve`

Methods: `"zscore"`, `"robust_zscore"`, `"none"`.  
Config: `preprocessing.normalization.method`

### 2.6 `features/timeseries.py` — `extract_features(lc, cfg) -> dict[str, float]`

Returns all 17 keys from §1.4. Config: `features.*`.  
Internal helper: `_lomb_scargle_dominant(t, y, cfg) -> tuple[float|None, float|None]` (min 15 points).

### 2.7 `detection/periodicity.py` — `estimate_periodicity(lc, cfg) -> PeriodicityResult`

Delegates to `_lomb_scargle_dominant`. Quality = `tanh(max(0, power))`.

### 2.8 `detection/anomaly.py` — `compute_anomaly(feature_rows, cfg) -> list[dict]`

Batch operation. Z-score floored sigma=1.0. IF requires n >= 8, normalized to [0,1].  
Config: `detection.anomaly.*`

### 2.9 `detection/scoring.py` — `score_candidate(candidate, cfg) -> CandidateScoreBreakdown`

Formulas per §1.7. Config: `detection.scoring.weights.*`

### 2.10 `validation/catalogs.py` — `CatalogValidator`

```python
class CatalogValidator:
    def validate(self, candidate: Candidate) -> ValidationResult: ...
```

Private methods `_query_simbad()` and `_query_vizier()` for test mocking.  
Config: `validation.radius_arcsec`, `validation.vizier_catalogs`

### 2.11 `reporting/plots.py`

```python
def plot_lightcurve(cfg, lc, *, out_path: Path) -> Path
def plot_periodogram(cfg, lc, *, out_path: Path) -> Path | None
```

8×3 inch, 160 DPI. Matplotlib Agg backend. Config: `reporting.max_points_plot`, `reporting.include_periodogram`.

### 2.12 `reporting/report_generator.py` — `generate_reports(cfg, candidates, *, top_k)`

Outputs per candidate: `{id}.json`, `{id}.md`, `{id}_lightcurve.png`, `{id}_periodogram.png`.  
Uses Jinja2 for Markdown. Must include scientific caveats section.

### 2.13 `persistence/database.py` — `Database`

```python
class Database:
    def __init__(self, path: Path) -> None: ...
    def connect(self) -> sqlite3.Connection: ...
```

### 2.14 `persistence/repositories.py` — `Repositories`

```python
@dataclass(frozen=True)
class Repositories:
    db: Database
    def init_schema(self) -> None: ...
    def insert_pipeline_run(self, run: PipelineRun) -> None: ...
    def upsert_target(self, lc: LightCurve) -> None: ...
    def upsert_candidate(self, run_id: str, cand: Candidate) -> None: ...
    def top_candidates(self, run_id: str, limit: int) -> list[dict[str, Any]]: ...
```

SQLite tables: `pipeline_runs`, `targets`, `candidates`. See §5 for full schema.

### 2.15 `pipeline/runner.py` — `run_pipeline()`

```python
def run_pipeline(
    cfg: SkyMinerConfig,
    *,
    mode: str,
    tic_ids: list[str] | None,
    coords: list[tuple[float, float]] | None,
    max_targets: int,
    validate: bool,
    detect: bool = True,
    report: bool = True,
    persist: bool = True,
) -> dict[str, Any]:
```

Returns: `{run_id, mode, targets_ingested, candidates_scored, outputs_dir, db_path}`

### 2.16 CLI Commands (`cli.py`)

Framework: `typer`. Entry point: `skyminer`.

| Command | Notes |
|---------|-------|
| `smoke-test` | Offline, no network, validate=False |
| `run-pipeline` | Full pipeline; `--mode`, `--tic`, `--ra`, `--dec`, `--max-targets` |
| `ingest` | detect=False, report=False |
| `validate` | detect=False, report=False |
| `rank-candidates` | report=False |
| `generate-report` | Full with reports |

---

## 3. Config Schema (config/default.yaml)

```yaml
mode: "local"

paths:
  data_dir: "data"
  outputs_dir: "outputs"
  db_path: "outputs/skyminer.sqlite"

logging:
  level: "INFO"
  file_name: "skyminer.log"

tess:
  mission: "TESS"
  author: "SPOC"
  cadence: "long"
  download_dir: "data/raw/tess_cache"
  max_lightcurves_per_target: 1

pipeline:
  batch_size: 4
  top_k_reports: 5

preprocessing:
  smoothing:
    enabled: true
    method: "savgol"
    window_length: 31
    polyorder: 2
  normalization:
    method: "robust_zscore"

features:
  autocorr_lags: [1, 2, 5, 10]
  peak_prominence: 1.0
  lomb_scargle:
    min_period_days: 0.05
    max_period_days: 20.0
    samples_per_peak: 10

detection:
  anomaly:
    use_isolation_forest: true
    zscore_threshold: 2.5
    isolation_forest:
      n_estimators: 200
      contamination: 0.1
      random_state: 42
  scoring:
    weights:
      anomaly: 0.45
      periodicity: 0.30
      variability: 0.20
      novelty: 0.05
    min_score_to_report: 0.2

validation:
  enabled: true
  radius_arcsec: 5.0
  vizier_catalogs:
    - "I/355/gaiadr3"

reporting:
  include_periodogram: true
  max_points_plot: 5000
```

---

## 4. Data Flow

```
1. INPUT          User provides TIC IDs, coordinates, or uses defaults
2. INGEST         BaseIngestor → list[LightCurve]
3. PERSIST TARGET upsert_target() → targets table
4. CLEAN          clean_lightcurve() → LightCurve (NaN removed, sorted, smoothed)
5. NORMALIZE      normalize_lightcurve() → LightCurve (flux normalized)
6. EXTRACT FEATS  extract_features() → dict[str, float]
7. PERIODICITY    estimate_periodicity() → PeriodicityResult
8. BUILD CANDS    Candidate(features, periodicity, anomaly={})
9. ANOMALY        compute_anomaly(all_feature_rows) → list[dict] (batch z-score + IF)
10. SCORE         score_candidate(cand) → CandidateScoreBreakdown
11. VALIDATE      CatalogValidator.validate(cand) → ValidationResult
12. PERSIST CANDS upsert_candidate() → candidates table
13. REPORT        generate_reports(top_k) → JSON + MD + PNG artifacts
14. RETURN        summary dict {run_id, mode, targets_ingested, ...}
```

---

## 5. SQLite Schema

```sql
pipeline_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  mode TEXT NOT NULL,
  config_json TEXT NOT NULL,
  params_json TEXT NOT NULL
)

targets (
  source TEXT NOT NULL,
  target_id TEXT NOT NULL,
  coord_json TEXT,
  meta_json TEXT,
  PRIMARY KEY (source, target_id)
)

candidates (
  candidate_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  source TEXT NOT NULL,
  target_id TEXT NOT NULL,
  coord_json TEXT,
  features_json TEXT NOT NULL,
  periodicity_json TEXT NOT NULL,
  anomaly_json TEXT NOT NULL,
  validation_json TEXT NOT NULL,
  score_json TEXT,
  notes_json TEXT,
  total_score REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  PRIMARY KEY (candidate_id, run_id),
  FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id) ON DELETE CASCADE
)
```

---

## 6. Key Design Decisions

1. **IsolationForest requires batch size >= 8** — falls back to z-score only for smaller batches.
2. **Anomaly detection is batch-scoped** — anomalousness relative to current batch peers.
3. **Robust z-score is the default** — resistant to astrophysical transients inflating mean/std.
4. **lightkurve and astroquery are optional** — guarded with ModuleNotFoundError; local mode uses CSV fixture.
5. **HistoricalStubIngestor is explicit** — schema already accepts `source="historical_stub"` without future migration.
6. **Validation does not trigger re-scoring** — conservative choice; callers must re-score manually if desired.
7. **SQLite upserts are idempotent** — ON CONFLICT DO UPDATE; same target in two runs creates two candidate rows.
8. **Reports include mandatory scientific caveats** — never state confirmed discovery; always use candidate language.

---

## Appendix A — File Map

| Path (relative to `src/skyminer/`) | Primary export |
|---|---|
| `models/schemas.py` | All Pydantic schemas |
| `config.py` | `SkyMinerConfig`, `default_config_path()` |
| `logging_config.py` | `setup_logging()` |
| `ingestion/base.py` | `BaseIngestor` |
| `ingestion/tess.py` | `TessIngestor` |
| `ingestion/historical_stub.py` | `HistoricalStubIngestor` |
| `preprocessing/cleaning.py` | `clean_lightcurve()` |
| `preprocessing/normalization.py` | `normalize_lightcurve()` |
| `features/timeseries.py` | `extract_features()`, `_lomb_scargle_dominant()` |
| `detection/periodicity.py` | `estimate_periodicity()` |
| `detection/anomaly.py` | `compute_anomaly()` |
| `detection/scoring.py` | `score_candidate()` |
| `validation/catalogs.py` | `CatalogValidator`, `VSXValidatorPlaceholder` |
| `reporting/plots.py` | `plot_lightcurve()`, `plot_periodogram()` |
| `reporting/report_generator.py` | `generate_reports()` |
| `persistence/database.py` | `Database` |
| `persistence/repositories.py` | `Repositories` |
| `pipeline/runner.py` | `run_pipeline()` |
| `cli.py` | `app` (typer CLI) |
| `utils/io.py` | `read_csv_lightcurve()`, `ensure_dir()` |
| `utils/coordinates.py` | coordinate helpers |
| `utils/retry.py` | retry decorator |
