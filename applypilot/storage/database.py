"""Database initialization and connection management."""

from pathlib import Path
import sqlite3
from typing import Union
import aiosqlite

from applypilot.storage.schema import CREATE_TABLES_SQL


def _enable_foreign_keys() -> None:
    """Ensure foreign key constraints are enabled by default for SQLite connections."""
    orig_connect = sqlite3.connect
    if getattr(orig_connect, "_ap_fk_enabled", False):
        return

    def custom_connect(*args, **kwargs):
        conn = orig_connect(*args, **kwargs)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    custom_connect._ap_fk_enabled = True  # type: ignore[attr-defined]
    sqlite3.connect = custom_connect


_enable_foreign_keys()


async def init_db(db_path: Union[Path, str]) -> None:
    """Initialize the SQLite database with WAL mode, foreign keys, and 10-table schema."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
