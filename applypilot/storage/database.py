"""Database initialization and connection management."""

from pathlib import Path
from typing import Union
import aiosqlite

from applypilot.storage.schema import CREATE_TABLES_SQL


async def init_db(db_path: Union[Path, str]) -> None:
    """Initialize the SQLite database with WAL mode, foreign keys, and 10-table schema."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
