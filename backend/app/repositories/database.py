"""Small async SQLite database adapter.

Learning note:
    SQL remains at the repository boundary instead of leaking into the domain.
    ``aiosqlite`` delegates SQLite calls away from the event loop while SQLite
    keeps local development simple and reproducible.
"""

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    """Own one SQLite connection and the schema lifecycle."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the database and enable relational integrity checks."""

        if self._connection is not None:
            return
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.commit()

    async def initialize(self) -> None:
        """Create the persistence schema if it does not exist."""

        connection = self._require_connection()
        await connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL REFERENCES players(id),
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed'))
            );

            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL UNIQUE REFERENCES games(id),
                player_id INTEGER NOT NULL REFERENCES players(id),
                score INTEGER NOT NULL CHECK (score >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_scores_score
                ON scores(score DESC);
            """
        )
        await connection.commit()

    async def execute(
        self,
        sql: str,
        parameters: Iterable[Any] = (),
    ) -> int:
        """Execute a statement and return its generated row id."""

        connection = self._require_connection()
        cursor = await connection.execute(sql, tuple(parameters))
        await connection.commit()
        return cursor.lastrowid

    async def fetch_one(
        self,
        sql: str,
        parameters: Iterable[Any] = (),
    ) -> Mapping[str, Any] | None:
        """Return one row, if a query matched."""

        connection = self._require_connection()
        cursor = await connection.execute(sql, tuple(parameters))
        return await cursor.fetchone()

    async def fetch_all(
        self,
        sql: str,
        parameters: Iterable[Any] = (),
    ) -> list[Mapping[str, Any]]:
        """Return all rows from a query."""

        connection = self._require_connection()
        cursor = await connection.execute(sql, tuple(parameters))
        return await cursor.fetchall()

    async def close(self) -> None:
        """Close the connection cleanly during application shutdown."""

        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database.connect() must run before database access")
        return self._connection
