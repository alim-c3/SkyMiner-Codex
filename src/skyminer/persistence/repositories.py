from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from skyminer.models.schemas import Candidate, LightCurve, PipelineRun
from skyminer.persistence.database import Database


@dataclass(frozen=True)
class Repositories:
    db: Database

    def init_schema(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(_SCHEMA_SQL)

    def insert_pipeline_run(self, run: PipelineRun) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pipeline_runs(run_id, started_at, mode, config_json, params_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.started_at.isoformat(),
                    run.mode,
                    json.dumps(run.model_dump(), default=str),
                    json.dumps(run.params, default=str),
                ),
            )

    def upsert_target(self, lc: LightCurve) -> None:
        with self.db.connect() as conn:
            coord = lc.coord.model_dump() if lc.coord is not None else None
            conn.execute(
                """
                INSERT INTO targets(source, target_id, coord_json, meta_json)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(source, target_id) DO UPDATE SET
                  coord_json=excluded.coord_json,
                  meta_json=excluded.meta_json
                """,
                (lc.source, lc.target_id, _j(coord), _j(lc.meta)),
            )

    def upsert_candidate(self, run_id: str, cand: Candidate) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO candidates(candidate_id, run_id, source, target_id, coord_json,
                                       features_json, periodicity_json, anomaly_json, validation_json,
                                       score_json, notes_json, total_score)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id, run_id) DO UPDATE SET
                  features_json=excluded.features_json,
                  periodicity_json=excluded.periodicity_json,
                  anomaly_json=excluded.anomaly_json,
                  validation_json=excluded.validation_json,
                  score_json=excluded.score_json,
                  notes_json=excluded.notes_json,
                  total_score=excluded.total_score
                """,
                (
                    cand.candidate_id,
                    run_id,
                    cand.source,
                    cand.target_id,
                    _j(cand.coord.model_dump() if cand.coord else None),
                    _j(cand.features),
                    _j(cand.periodicity.model_dump()),
                    _j(cand.anomaly),
                    _j(cand.validation.model_dump()),
                    _j(cand.score.model_dump() if cand.score else None),
                    _j(cand.notes),
                    float(cand.score.total if cand.score else 0.0),
                ),
            )

    def top_candidates(self, run_id: str, limit: int) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT candidate_id, total_score, validation_json
                FROM candidates
                WHERE run_id = ?
                ORDER BY total_score DESC, candidate_id ASC
                LIMIT ?
                """,
                (run_id, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]


def _j(v: Any) -> str | None:
    if v is None:
        return None
    return json.dumps(v, default=str)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  mode TEXT NOT NULL,
  config_json TEXT NOT NULL,
  params_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
  source TEXT NOT NULL,
  target_id TEXT NOT NULL,
  coord_json TEXT,
  meta_json TEXT,
  PRIMARY KEY (source, target_id)
);

CREATE TABLE IF NOT EXISTS candidates (
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
);
"""

