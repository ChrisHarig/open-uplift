"""Shared fixtures for plugin tests."""

import sqlite3

import pytest

from open_uplift.db import SCHEMA_SQL, _migrate_db
from open_uplift.config import DEFAULT_PRICING


@pytest.fixture
def db(tmp_path):
    """In-memory SQLite with full schema for plugin tests."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    conn.executescript(SCHEMA_SQL)

    for model_name, prices in DEFAULT_PRICING.items():
        conn.execute(
            """INSERT OR IGNORE INTO model_pricing
               (model_name, input_cost_per_mtok, output_cost_per_mtok,
                cache_read_per_mtok, cache_create_per_mtok)
               VALUES (?, ?, ?, ?, ?)""",
            (model_name, prices["input"], prices["output"],
             prices["cache_read"], prices["cache_create"]),
        )

    _migrate_db(conn)
    conn.commit()

    yield conn
    conn.close()
