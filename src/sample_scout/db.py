"""Base SQLite de la librería. Los archivos nunca se mueven: el orden es solo un índice."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS roots (path TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    root TEXT NOT NULL,
    name TEXT NOT NULL,
    folder TEXT NOT NULL,
    size INTEGER,
    mtime REAL,
    duration REAL,
    kind TEXT,
    kind_source TEXT,
    bpm REAL,
    bpm_source TEXT,
    key TEXT,
    key_source TEXT,
    instrument TEXT,
    instrument_source TEXT,
    analyzed INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_samples_root ON samples(root);
CREATE INDEX IF NOT EXISTS idx_samples_instrument ON samples(instrument);
CREATE INDEX IF NOT EXISTS idx_samples_analyzed ON samples(analyzed);
"""


def default_db_path() -> Path:
    if os.environ.get("SAMPLE_SCOUT_DB"):  # para pruebas o para tener varias librerías
        return Path(os.environ["SAMPLE_SCOUT_DB"])
    base = Path(os.environ.get("APPDATA") or Path.home()) / "SampleScout"
    base.mkdir(parents=True, exist_ok=True)
    return base / "library.db"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or default_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def list_roots(conn: sqlite3.Connection) -> list[str]:
    return [r["path"] for r in conn.execute("SELECT path FROM roots ORDER BY path")]


def add_root(conn: sqlite3.Connection, path: str) -> None:
    conn.execute("INSERT OR IGNORE INTO roots(path) VALUES (?)", (path,))
    conn.commit()


def remove_root(conn: sqlite3.Connection, path: str) -> None:
    conn.execute("DELETE FROM samples WHERE root = ?", (path,))
    conn.execute("DELETE FROM roots WHERE path = ?", (path,))
    conn.commit()


def search(conn: sqlite3.Connection, text: str = "", instrument: str | None = None,
           kind: str | None = None, bpm_min: float | None = None, bpm_max: float | None = None,
           key: str | None = None, limit: int = 20000) -> list[dict]:
    where: list[str] = []
    params: list = []
    for word in text.lower().split():
        where.append("lower(path) LIKE ?")
        params.append(f"%{word}%")
    if instrument == "__none__":
        where.append("instrument IS NULL")
    elif instrument:
        where.append("instrument = ?")
        params.append(instrument)
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if bpm_min:
        where.append("bpm >= ?")
        params.append(bpm_min)
    if bpm_max:
        where.append("bpm <= ?")
        params.append(bpm_max)
    if key:
        where.append("key = ?")
        params.append(key)
    sql = "SELECT * FROM samples"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY name COLLATE NOCASE LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


def instrument_counts(conn: sqlite3.Connection) -> dict[str | None, int]:
    rows = conn.execute("SELECT instrument, COUNT(*) AS n FROM samples GROUP BY instrument")
    return {r["instrument"]: r["n"] for r in rows}


def stats(conn: sqlite3.Connection) -> tuple[int, int]:
    """(total de samples, pendientes de análisis)"""
    row = conn.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(analyzed = 0), 0) AS pending FROM samples"
    ).fetchone()
    return row["total"], row["pending"]
