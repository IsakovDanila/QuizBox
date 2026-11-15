from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .migrate import DEFAULT_DATABASE, migrate

_configured_path = os.getenv("QUIZBOX_DB_PATH")
DB_PATH = Path(_configured_path).expanduser() if _configured_path else DEFAULT_DATABASE
if not DB_PATH.is_absolute():
    DB_PATH = (Path.cwd() / DB_PATH).resolve()

_initialized = False
_initialize_lock = threading.Lock()


def configure_database(path: str | Path) -> None:
    """Override the DB path (mostly for tests)."""
    global DB_PATH, _initialized
    candidate = Path(path).expanduser()
    DB_PATH = candidate if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
    _initialized = False


def initialize_database() -> int:
    global _initialized
    if _initialized:
        return 0
    with _initialize_lock:
        if _initialized:
            return 0
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        version = migrate(DB_PATH)
        _initialized = True
        return version


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    initialize_database()
    conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
