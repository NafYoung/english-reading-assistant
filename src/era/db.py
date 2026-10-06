from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from era.config import AppConfig, load_config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(config: AppConfig | None = None, attach_dict: bool = True) -> sqlite3.Connection:
    cfg = config or load_config()
    cfg.paths.ensure()
    conn = sqlite3.connect(cfg.paths.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    if attach_dict and cfg.paths.dict_path.exists():
        attach_ecdict(conn, cfg.paths.dict_path)
    return conn


def attach_ecdict(conn: sqlite3.Connection, dict_path: Path) -> None:
    try:
        conn.execute("DETACH DATABASE ecdict")
    except sqlite3.OperationalError:
        pass
    conn.execute("ATTACH DATABASE ? AS ecdict", (str(dict_path),))


def dict_ready(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM pragma_database_list WHERE name = 'ecdict'"
    ).fetchone()
    return row is not None


def dict_count(conn: sqlite3.Connection) -> int:
    if not dict_ready(conn):
        return 0
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM ecdict.dict").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["n"] if row else 0)


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT)"
    )
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.name
        if version in applied:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, utcnow()),
        )
    conn.commit()
