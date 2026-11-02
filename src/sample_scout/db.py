"""Base SQLite de la librería. Los archivos nunca se mueven: el orden es solo un índice."""

from __future__ import annotations

import os
import sqlite3
import time
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
    error TEXT,
    cover TEXT  -- ruta de la portada del pack (ver scanner.CoverFinder)
);
CREATE INDEX IF NOT EXISTS idx_samples_root ON samples(root);
CREATE INDEX IF NOT EXISTS idx_samples_instrument ON samples(instrument);
CREATE INDEX IF NOT EXISTS idx_samples_analyzed ON samples(analyzed);

-- Datos del usuario: van aparte y por ruta, así sobreviven a re-escanear y a quitar y volver
-- a agregar una carpeta (las filas de `samples` se borran y se regeneran; estas no).
CREATE TABLE IF NOT EXISTS marks (
    path TEXT PRIMARY KEY,
    favorite INTEGER NOT NULL DEFAULT 0,
    rating INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_fields (
    path TEXT NOT NULL,
    field TEXT NOT NULL,
    value,  -- NULL = el usuario dejó el dato vacío a propósito
    PRIMARY KEY (path, field)
);
CREATE TABLE IF NOT EXISTS tags (
    path TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (path, tag)
);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS collection_items (
    collection_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    added REAL NOT NULL,
    PRIMARY KEY (collection_id, path)
);
CREATE TABLE IF NOT EXISTS history (
    path TEXT PRIMARY KEY,
    played REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_played ON history(played);
"""

SCHEMA_VERSION = 2  # 1 (o 0, sin marcar) = solo `roots` y `samples`, la de 0.1.0
# Columnas sumadas a `samples` después de crearla: (nombre, tipo)
ADDED_COLUMNS = (("cover", "TEXT"),)
EDITABLE_FIELDS = ("kind", "bpm", "key", "instrument")
HISTORY_SIZE = 200


def default_db_path() -> Path:
    """%APPDATA%\\SampleScout\\library.db, o lo que diga SAMPLE_SCOUT_DB."""
    if os.environ.get("SAMPLE_SCOUT_DB"):  # para pruebas o para tener varias librerías
        return Path(os.environ["SAMPLE_SCOUT_DB"])
    base = Path(os.environ.get("APPDATA") or Path.home()) / "SampleScout"
    base.mkdir(parents=True, exist_ok=True)
    return base / "library.db"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Abre la base (creando o migrando el esquema) en modo WAL, para que la ventana lea mientras
    el hilo de escaneo escribe. Cada hilo usa su propia conexión."""
    conn = sqlite3.connect(str(path or default_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Lleva una base de cualquier versión anterior a la actual sin perder datos: las tablas
    nuevas se crean vacías y `roots` / `samples` quedan como estaban."""
    conn.executescript(SCHEMA)
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(samples)")}
    for name, kind in ADDED_COLUMNS:
        if name not in columns:
            conn.execute(f"ALTER TABLE samples ADD COLUMN {name} {kind}")
    if conn.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()


def list_roots(conn: sqlite3.Connection) -> list[str]:
    """Carpetas raíz que el usuario agregó a la librería."""
    return [r["path"] for r in conn.execute("SELECT path FROM roots ORDER BY path")]


def add_root(conn: sqlite3.Connection, path: str) -> None:
    """Registra una carpeta raíz (el escaneo se lanza aparte)."""
    conn.execute("INSERT OR IGNORE INTO roots(path) VALUES (?)", (path,))
    conn.commit()


def remove_root(conn: sqlite3.Connection, path: str) -> None:
    """Quita la carpeta y sus samples del índice. Los archivos del disco no se tocan, y los datos
    del usuario (favoritos, tags, colecciones…) quedan guardados por si se vuelve a agregar."""
    conn.execute("DELETE FROM samples WHERE root = ?", (path,))
    conn.execute("DELETE FROM roots WHERE path = ?", (path,))
    conn.commit()


SELECT_SAMPLES = """
SELECT s.*, COALESCE(m.favorite, 0) AS favorite, COALESCE(m.rating, 0) AS rating,
       (SELECT group_concat(tag, ', ') FROM (SELECT tag FROM tags t WHERE t.path = s.path
                                             ORDER BY tag COLLATE NOCASE)) AS tags
FROM samples s LEFT JOIN marks m ON m.path = s.path
"""


def search(conn: sqlite3.Connection, text: str = "", instrument: str | None = None,
           kind: str | None = None, bpm_min: float | None = None, bpm_max: float | None = None,
           key: str | None = None, favorites: bool = False, min_rating: int = 0,
           tag: str | None = None, collection: int | None = None, history: bool = False,
           limit: int = 20000) -> list[dict]:
    """Samples que cumplen todos los filtros, ordenados por nombre. `text` busca cada palabra en
    la ruta completa (nombre, carpetas, pack) y en los tags. `instrument="__none__"` trae los
    sin clasificar. `collection` es el id de una colección; con `history` solo vienen los
    escuchados, del más reciente al más viejo. Los filtros en None (o 0) no filtran.
    Cada fila trae además `favorite`, `rating` y `tags` (separados por coma)."""
    where: list[str] = []
    params: list = []
    for word in text.lower().split():
        where.append("(lower(s.path) LIKE ? OR EXISTS (SELECT 1 FROM tags t "
                     "WHERE t.path = s.path AND lower(t.tag) LIKE ?))")
        params += [f"%{word}%"] * 2
    if instrument == "__none__":
        where.append("s.instrument IS NULL")
    elif instrument:
        where.append("s.instrument = ?")
        params.append(instrument)
    if kind:
        where.append("s.kind = ?")
        params.append(kind)
    if bpm_min:
        where.append("s.bpm >= ?")
        params.append(bpm_min)
    if bpm_max:
        where.append("s.bpm <= ?")
        params.append(bpm_max)
    if key:
        where.append("s.key = ?")
        params.append(key)
    if favorites:
        where.append("m.favorite = 1")
    if min_rating:
        where.append("m.rating >= ?")
        params.append(min_rating)
    if tag:
        where.append("EXISTS (SELECT 1 FROM tags t WHERE t.path = s.path AND t.tag = ?)")
        params.append(tag)
    if collection is not None:
        where.append("EXISTS (SELECT 1 FROM collection_items c "
                     "WHERE c.path = s.path AND c.collection_id = ?)")
        params.append(collection)
    sql = SELECT_SAMPLES
    if history:
        sql += " JOIN history h ON h.path = s.path"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + ("h.played DESC" if history else "s.name COLLATE NOCASE") + " LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


def get_samples(conn: sqlite3.Connection, paths: list[str]) -> dict[str, dict]:
    """Las filas de esas rutas (con favorito, estrellas y tags), por ruta."""
    rows = {}
    for path in paths:
        row = conn.execute(SELECT_SAMPLES + " WHERE s.path = ?", (path,)).fetchone()
        if row:
            rows[path] = dict(row)
    return rows


def instrument_counts(conn: sqlite3.Connection) -> dict[str | None, int]:
    """Cantidad de samples por instrumento (la clave None son los sin clasificar)."""
    rows = conn.execute("SELECT instrument, COUNT(*) AS n FROM samples GROUP BY instrument")
    return {r["instrument"]: r["n"] for r in rows}


def stats(conn: sqlite3.Connection) -> tuple[int, int]:
    """(total de samples, pendientes de análisis)"""
    row = conn.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(analyzed = 0), 0) AS pending FROM samples"
    ).fetchone()
    return row["total"], row["pending"]


# --- Favoritos y estrellas ---
def set_favorite(conn: sqlite3.Connection, paths: list[str], favorite: bool) -> None:
    """Marca o desmarca esos samples como favoritos."""
    conn.executemany(
        "INSERT INTO marks(path, favorite) VALUES (?, ?) "
        "ON CONFLICT(path) DO UPDATE SET favorite = excluded.favorite",
        [(p, int(favorite)) for p in paths])
    conn.commit()


def set_rating(conn: sqlite3.Connection, paths: list[str], rating: int) -> None:
    """Pone de 0 a 5 estrellas a esos samples."""
    rating = max(0, min(5, int(rating)))
    conn.executemany(
        "INSERT INTO marks(path, rating) VALUES (?, ?) "
        "ON CONFLICT(path) DO UPDATE SET rating = excluded.rating",
        [(p, rating) for p in paths])
    conn.commit()


# --- Datos corregidos a mano ---
def set_user_field(conn: sqlite3.Connection, paths: list[str], field: str, value) -> None:
    """Guarda un dato corregido por el usuario (fuente `user`). Gana sobre lo que salga de la
    metadata, el nombre o el audio, y ni re-escanear ni re-analizar lo pisan. `value=None` deja
    el dato vacío a propósito."""
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Campo no editable: {field}")
    conn.executemany(
        "INSERT INTO user_fields(path, field, value) VALUES (?, ?, ?) "
        "ON CONFLICT(path, field) DO UPDATE SET value = excluded.value",
        [(p, field, value) for p in paths])
    conn.executemany(f"UPDATE samples SET {field} = ?, {field}_source = 'user' WHERE path = ?",
                     [(value, p) for p in paths])
    conn.commit()


def clear_user_fields(conn: sqlite3.Connection, paths: list[str]) -> None:
    """Olvida las correcciones manuales de esos samples y los deja marcados para re-indexar
    (mtime en NULL): el próximo escaneo vuelve a calcular sus datos."""
    conn.executemany("DELETE FROM user_fields WHERE path = ?", [(p,) for p in paths])
    conn.executemany("UPDATE samples SET mtime = NULL WHERE path = ?", [(p,) for p in paths])
    conn.commit()


def apply_user_fields(conn: sqlite3.Connection, path: str) -> None:
    """Pisa la fila de `samples` con las correcciones manuales (lo usa el escaneo)."""
    for r in conn.execute("SELECT field, value FROM user_fields WHERE path = ?", (path,)):
        if r["field"] in EDITABLE_FIELDS:
            conn.execute(f"UPDATE samples SET {r['field']} = ?, {r['field']}_source = 'user' "
                         "WHERE path = ?", (r["value"], path))


# --- Tags ---
def add_tags(conn: sqlite3.Connection, paths: list[str], tags: list[str]) -> None:
    """Agrega tags libres (sin espacios de más; los repetidos se ignoran)."""
    tags = [t.strip() for t in tags if t.strip()]
    conn.executemany("INSERT OR IGNORE INTO tags(path, tag) VALUES (?, ?)",
                     [(p, t) for p in paths for t in tags])
    conn.commit()


def remove_tags(conn: sqlite3.Connection, paths: list[str], tags: list[str]) -> None:
    """Quita esos tags de esos samples."""
    conn.executemany("DELETE FROM tags WHERE path = ? AND tag = ?",
                     [(p, t) for p in paths for t in tags])
    conn.commit()


def all_tags(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Tags usados por samples de la librería, con su cantidad, en orden alfabético."""
    rows = conn.execute(
        "SELECT t.tag, COUNT(*) AS n FROM tags t JOIN samples s ON s.path = t.path "
        "GROUP BY t.tag ORDER BY t.tag COLLATE NOCASE")
    return [(r["tag"], r["n"]) for r in rows]


# --- Colecciones ---
def list_collections(conn: sqlite3.Connection) -> list[dict]:
    """Colecciones (id, name y n = samples presentes en la librería), por nombre."""
    rows = conn.execute(
        "SELECT c.id, c.name, COUNT(s.path) AS n FROM collections c "
        "LEFT JOIN collection_items i ON i.collection_id = c.id "
        "LEFT JOIN samples s ON s.path = i.path "
        "GROUP BY c.id ORDER BY c.name COLLATE NOCASE")
    return [dict(r) for r in rows]


def create_collection(conn: sqlite3.Connection, name: str) -> int:
    """Crea una colección y devuelve su id. sqlite3.IntegrityError si el nombre ya existe."""
    cur = conn.execute("INSERT INTO collections(name) VALUES (?)", (name.strip(),))
    conn.commit()
    return cur.lastrowid


def rename_collection(conn: sqlite3.Connection, collection: int, name: str) -> None:
    """Cambia el nombre. sqlite3.IntegrityError si ya hay otra con ese nombre."""
    conn.execute("UPDATE collections SET name = ? WHERE id = ?", (name.strip(), collection))
    conn.commit()


def delete_collection(conn: sqlite3.Connection, collection: int) -> None:
    """Borra la colección. Los samples siguen en la librería."""
    conn.execute("DELETE FROM collection_items WHERE collection_id = ?", (collection,))
    conn.execute("DELETE FROM collections WHERE id = ?", (collection,))
    conn.commit()


def add_to_collection(conn: sqlite3.Connection, collection: int, paths: list[str]) -> None:
    """Agrega samples a una colección (los que ya estaban quedan igual)."""
    now = time.time()
    conn.executemany(
        "INSERT OR IGNORE INTO collection_items(collection_id, path, added) VALUES (?, ?, ?)",
        [(collection, p, now) for p in paths])
    conn.commit()


def remove_from_collection(conn: sqlite3.Connection, collection: int, paths: list[str]) -> None:
    """Saca samples de una colección."""
    conn.executemany("DELETE FROM collection_items WHERE collection_id = ? AND path = ?",
                     [(collection, p) for p in paths])
    conn.commit()


# --- Historial ---
def add_history(conn: sqlite3.Connection, path: str) -> None:
    """Anota que se escuchó un sample y deja solo los últimos HISTORY_SIZE."""
    conn.execute("INSERT INTO history(path, played) VALUES (?, ?) "
                 "ON CONFLICT(path) DO UPDATE SET played = excluded.played",
                 (path, time.time()))
    conn.execute("DELETE FROM history WHERE path NOT IN "
                 "(SELECT path FROM history ORDER BY played DESC LIMIT ?)", (HISTORY_SIZE,))
    conn.commit()


def history_count(conn: sqlite3.Connection) -> int:
    """Cuántos samples del historial siguen en la librería."""
    return conn.execute("SELECT COUNT(*) FROM history h JOIN samples s ON s.path = h.path"
                        ).fetchone()[0]


def clear_history(conn: sqlite3.Connection) -> None:
    """Vacía el historial de escucha."""
    conn.execute("DELETE FROM history")
    conn.commit()
