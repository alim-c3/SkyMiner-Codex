from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


class PathsConfig(BaseModel):
    data_dir: Path = Path("data")
    outputs_dir: Path = Path("outputs")
    db_path: Path = Path("outputs/skyminer.sqlite")


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file_name: str = "skyminer.log"


class TessConfig(BaseModel):
    mission: str = "TESS"
    author: str = "SPOC"
    cadence: str = "long"
    download_dir: Path = Path("data/raw/tess_cache")
    max_lightcurves_per_target: int = 1


class PipelineConfig(BaseModel):
    batch_size: int = 4
    top_k_reports: int = 5


class SmoothingConfig(BaseModel):
    enabled: bool = True
    method: Literal["savgol", "none"] = "savgol"
    window_length: int = 31
    polyorder: int = 2


class NormalizationConfig(BaseModel):
    method: Literal["zscore", "robust_zscore", "none"] = "robust_zscore"


class PreprocessingConfig(BaseModel):
    smoothing: SmoothingConfig = Field(default_factory=SmoothingConfig)
    normalization: NormalizationConfig = Field(default_factory=NormalizationConfig)


class LombScargleConfig(BaseModel):
    min_period_days: float = 0.05
    max_period_days: float = 20.0
    samples_per_peak: int = 10


class FeaturesConfig(BaseModel):
    autocorr_lags: list[int] = Field(default_factory=lambda: [1, 2, 5, 10])
    peak_prominence: float = 1.0
    lomb_scargle: LombScargleConfig = Field(default_factory=LombScargleConfig)


class IsolationForestConfig(BaseModel):
    n_estimators: int = 200
    contamination: float = 0.1
    random_state: int = 42


class AnomalyConfig(BaseModel):
    use_isolation_forest: bool = True
    zscore_threshold: float = 2.5
    isolation_forest: IsolationForestConfig = Field(default_factory=IsolationForestConfig)


class ScoringWeights(BaseModel):
    anomaly: float = 0.45
    periodicity: float = 0.30
    variability: float = 0.20
    novelty: float = 0.05


class ScoringConfig(BaseModel):
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    min_score_to_report: float = 0.2


class DetectionConfig(BaseModel):
    anomaly: AnomalyConfig = Field(default_factory=AnomalyConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)


class ValidationConfig(BaseModel):
    enabled: bool = True
    radius_arcsec: float = 5.0
    vizier_catalogs: list[str] = Field(default_factory=lambda: ["I/355/gaiadr3"])


class ReportingConfig(BaseModel):
    include_periodogram: bool = True
    max_points_plot: int = 5000


class RecentMASTConfig(BaseModel):
    # Operational definition of "last night": last N hours in UTC for MAST queries.
    hours: int = 24
    # Safety cap to avoid accidentally trying to ingest tens of thousands of targets at once.
    max_tic_ids: int = 500


class SkyMinerConfig(BaseModel):
    mode: Literal["local", "live"] = "local"

    paths: PathsConfig = Field(default_factory=PathsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    tess: TessConfig = Field(default_factory=TessConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)
    recent_mast: RecentMASTConfig = Field(default_factory=RecentMASTConfig)

    @classmethod
    def load(cls, path: Path) -> "SkyMinerConfig":
        raw = _load_yaml(path)
        cfg = cls.model_validate(raw)
        return _apply_env_overrides(cfg)

    def resolve_paths(self, repo_root: Path) -> "SkyMinerConfig":
        paths = self.paths.model_copy(
            update={
                "data_dir": _resolve(repo_root, self.paths.data_dir),
                "outputs_dir": _resolve(repo_root, self.paths.outputs_dir),
                "db_path": _resolve(repo_root, self.paths.db_path),
            }
        )
        tess = self.tess.model_copy(update={"download_dir": _resolve(repo_root, self.tess.download_dir)})
        return self.model_copy(update={"paths": paths, "tess": tess})


def default_config_path() -> Path:
    return Path(os.environ.get("SKYMINER_CONFIG_PATH", "config/default.yaml"))


def _resolve(root: Path, p: Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else (root / p).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
    else:
        data = _minimal_yaml_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping, got: {type(data)}")
    return data


def _apply_env_overrides(cfg: SkyMinerConfig) -> SkyMinerConfig:
    overrides: dict[str, Any] = {}
    if os.environ.get("SKYMINER_MODE"):
        overrides["mode"] = os.environ["SKYMINER_MODE"].strip()
    if os.environ.get("SKYMINER_LOG_LEVEL"):
        overrides["logging"] = cfg.logging.model_copy(update={"level": os.environ["SKYMINER_LOG_LEVEL"].strip()})
    if os.environ.get("SKYMINER_DB_PATH"):
        overrides["paths"] = cfg.paths.model_copy(update={"db_path": Path(os.environ["SKYMINER_DB_PATH"].strip())})
    return cfg.model_copy(update=overrides) if overrides else cfg


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    raw_lines: list[tuple[int, str]] = []
    for ln in text.splitlines():
        if not ln.strip() or ln.strip().startswith("#"):
            continue
        indent = len(ln) - len(ln.lstrip(" "))
        raw_lines.append((indent, ln.strip()))

    def parse_map(i: int, indent: int) -> tuple[dict[str, Any], int]:
        out: dict[str, Any] = {}
        while i < len(raw_lines):
            ind, content = raw_lines[i]
            if ind < indent:
                break
            if ind > indent:
                raise ValueError("Invalid YAML indentation (unexpected indent)")
            if content.startswith("- "):
                raise ValueError("Invalid YAML: list item where mapping key expected")
            if ":" not in content:
                raise ValueError(f"Invalid YAML line: {content}")
            key, rest = content.split(":", 1)
            key = key.strip()
            rest = rest.strip()
            i += 1
            if rest != "":
                out[key] = _parse_scalar(rest)
                continue
            if i >= len(raw_lines):
                out[key] = {}
                continue
            next_ind, next_content = raw_lines[i]
            if next_ind <= ind:
                out[key] = {}
                continue
            if next_content.startswith("- "):
                lst, i = parse_list(i, indent=next_ind)
                out[key] = lst
            else:
                mp, i = parse_map(i, indent=next_ind)
                out[key] = mp
        return out, i

    def parse_list(i: int, indent: int) -> tuple[list[Any], int]:
        out: list[Any] = []
        while i < len(raw_lines):
            ind, content = raw_lines[i]
            if ind < indent:
                break
            if ind != indent:
                raise ValueError("Invalid YAML indentation inside list")
            if not content.startswith("- "):
                break
            out.append(_parse_scalar(content[2:].strip()))
            i += 1
        return out, i

    parsed, _ = parse_map(0, indent=0)
    return parsed


def _parse_scalar(s: str) -> Any:
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        return s[1:-1]
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        return s[1:-1]
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        pass
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        parts = [p.strip() for p in inner.split(",")]
        return [_parse_scalar(p) for p in parts]
    return s
