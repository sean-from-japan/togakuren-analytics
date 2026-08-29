"""SQLite storage. Opening a database creates or migrates it in place."""

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(path):
    """Open ``path``, applying the schema. ``:memory:`` works for tests."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def upsert(conn, table, rows, columns):
    """Insert or replace ``rows`` (dicts) into ``table``."""
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    conn.executemany(sql, [[row.get(column) for column in columns] for row in rows])
    return len(rows)


def counts(conn):
    """Row count per table, for reporting after an ingest."""
    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def drop_personal_data(conn):
    """Remove every column that names or describes a person.

    Leaves ``player_id`` intact everywhere, so all match analysis still runs.
    """
    # squad_members references players, so it has to go first.
    conn.execute("DELETE FROM squad_members")
    conn.execute("DELETE FROM players")
    conn.execute("UPDATE game_teams SET manager = NULL")
    conn.commit()
