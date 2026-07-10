import sqlite3
import os
from contextlib import contextmanager

DATABASE_PATH = os.getenv("DATABASE_PATH", "dreamcheck.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id             TEXT PRIMARY KEY,
                prompt         TEXT NOT NULL,
                model          TEXT NOT NULL,
                prompt_pattern TEXT NOT NULL DEFAULT 'other',
                state          TEXT NOT NULL DEFAULT 'queued',
                failure_reason TEXT,
                asset_type     TEXT DEFAULT 'image',
                asset_url      TEXT,
                created_at     TEXT NOT NULL,
                completed_at   TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id             TEXT PRIMARY KEY,
                generation_id  TEXT NOT NULL REFERENCES generations(id),
                decision       TEXT NOT NULL,
                note           TEXT,
                created_at     TEXT NOT NULL
            )
        """)
