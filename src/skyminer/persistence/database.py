from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """Small sqlite3 wrapper.

    We use SQLite for a self-contained, reproducible MVP. This design supports repeated runs
    and avoids duplicate work by using stable IDs and uniqueness constraints.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

