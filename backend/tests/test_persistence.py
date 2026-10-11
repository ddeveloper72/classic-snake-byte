"""Repository-level tests using an isolated in-memory SQLite database."""

import asyncio

from backend.app.domain.game import GameEngine
from backend.app.repositories.database import Database
from backend.app.services.persistence import PersistenceService


def test_only_level_ten_winners_are_saved_to_leaderboard() -> None:
    async def scenario() -> None:
        database = Database(":memory:")
        persistence = PersistenceService(database, "Test Pilot")
        await persistence.initialize()

        losing_game_id = await persistence.start_game()
        loss = GameEngine(seed=1).state
        loss.score = 900
        loss.level = 9
        await persistence.complete_game(loss)

        winning_game_id = await persistence.start_game()
        victory = GameEngine(seed=2).state
        victory.score = 1500
        victory.level = 10
        victory.game_won = True
        await persistence.complete_game(victory)

        scores = await persistence.leaderboard()
        assert losing_game_id > 0
        assert winning_game_id > losing_game_id
        assert [dict(score) for score in scores] == [
            {
                "name": "Test Pilot",
                "score": 1500,
                "created_at": scores[0]["created_at"],
            }
        ]

        await persistence.close()

    asyncio.run(scenario())


def test_leaderboard_returns_only_the_top_ten_winners() -> None:
    async def scenario() -> None:
        database = Database(":memory:")
        persistence = PersistenceService(database, "Fallback")
        await persistence.initialize()

        for index in range(12):
            await persistence.start_game(f"Winner {index}")
            victory = GameEngine(seed=index).state
            victory.score = 1000 + index
            victory.level = 10
            victory.game_won = True
            await persistence.complete_game(victory)

        scores = await persistence.leaderboard()
        assert len(scores) == 10
        assert [score["score"] for score in scores] == list(
            range(1011, 1001, -1)
        )

        await persistence.close()

    asyncio.run(scenario())


def test_player_name_sql_payload_is_stored_as_data() -> None:
    async def scenario() -> None:
        payload = "Robert'); DROP TABLE scores;--"
        database = Database(":memory:")
        persistence = PersistenceService(database, payload)
        await persistence.initialize()

        await persistence.start_game()
        victory = GameEngine(seed=3).state
        victory.score = 2000
        victory.level = 10
        victory.game_won = True
        await persistence.complete_game(victory)

        scores = await persistence.leaderboard()
        assert [score["name"] for score in scores] == [payload]
        count = await database.fetch_one("SELECT COUNT(*) AS total FROM scores")
        assert count is not None
        assert dict(count) == {"total": 1}

        await persistence.close()

    asyncio.run(scenario())


def test_existing_database_is_migrated_for_victory_metadata() -> None:
    async def scenario() -> None:
        database = Database(":memory:")
        await database.connect()
        await database.execute(
            """
            CREATE TABLE games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active'
            )
            """
        )

        await database.initialize()

        columns = await database.fetch_all("PRAGMA table_info(games)")
        names = {column["name"] for column in columns}
        assert {"final_level", "game_won"} <= names

        await database.close()

    asyncio.run(scenario())
