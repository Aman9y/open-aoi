"""SQLite connection + schema for the inspection history."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inspections (
    inspection_id      TEXT PRIMARY KEY,
    timestamp          TEXT NOT NULL,
    reference_id       TEXT NOT NULL,
    profile_kind       TEXT NOT NULL,
    status             TEXT NOT NULL,
    reason             TEXT NOT NULL,
    overall_confidence REAL NOT NULL,
    inspection_time_ms INTEGER NOT NULL,
    defect_count       INTEGER NOT NULL,
    result_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inspections_ts     ON inspections(timestamp);
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(status);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
