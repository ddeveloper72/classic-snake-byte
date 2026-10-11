"""Application-level persistence orchestration."""

from collections.abc import Mapping
from datetime import UTC, datetime

from backend.app.domain.game import GameState
from backend.app.repositories.database import Database


class PersistenceService:
    """Persist the current player, game lifecycle, and completed scores."""

    def __init__(self, database: Database, player_name: str) -> None:
        self._database = database
        self._player_name = player_name
        self._player_id: int | None = None
        self._current_game_id: int | None = None

    async def initialize(self) -> None:
        """Open storage, create tables, and load the local player."""

        await self._database.connect()
        await self._database.initialize()
        player = await self._database.fetch_one(
            "SELECT id FROM players WHERE name = ?",
            (self._player_name,),
        )
        if player is None:
            self._player_id = await self._database.execute(
                "INSERT INTO players (name) VALUES (?)",
                (self._player_name,),
            )
        else:
            self._player_id = int(player["id"])

    async def start_game(self) -> int:
        """Create a persistent active game and return its id."""

        player_id = self._require_player()
        if self._current_game_id is not None:
            await self._database.execute(
                """
                UPDATE games
                SET status = 'completed', ended_at = ?, score = 0
                WHERE id = ? AND status = 'active'
                """,
                (self._now(), self._current_game_id),
            )
        self._current_game_id = await self._database.execute(
            "INSERT INTO games (player_id) VALUES (?)",
            (player_id,),
        )
        return self._current_game_id

    async def complete_game(self, state: GameState) -> None:
        """Mark the active game complete and write its final score once."""

        if self._current_game_id is None:
            return
        game_id = self._current_game_id
        player_id = self._require_player()
        await self._database.execute(
            """
            UPDATE games
            SET status = 'completed', ended_at = ?, score = ?
            WHERE id = ? AND status = 'active'
            """,
            (self._now(), state.score, game_id),
        )
        await self._database.execute(
            """
            INSERT OR IGNORE INTO scores (game_id, player_id, score)
            VALUES (?, ?, ?)
            """,
            (game_id, player_id, state.score),
        )
        self._current_game_id = None

    async def leaderboard(self, limit: int = 10) -> list[Mapping[str, object]]:
        """Return the highest completed scores for the leaderboard API."""

        return await self._database.fetch_all(
            """
            SELECT scores.score, players.name, scores.created_at
            FROM scores
            JOIN players ON players.id = scores.player_id
            ORDER BY scores.score DESC, scores.created_at ASC
            LIMIT ?
            """,
            (limit,),
        )

    async def close(self) -> None:
        """Close the underlying database."""

        await self._database.close()

    def _require_player(self) -> int:
        if self._player_id is None:
            raise RuntimeError("PersistenceService.initialize() must run first")
        return self._player_id

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
