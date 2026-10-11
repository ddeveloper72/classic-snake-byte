"""Repository-level tests using an isolated in-memory SQLite database."""

import asyncio

from backend.app.domain.game import GameEngine
from backend.app.repositories.database import Database
from backend.app.services.persistence import PersistenceService


def test_completed_game_is_saved_to_leaderboard() -> None:
    async def scenario() -> None:
        database = Database(":memory:")
        persistence = PersistenceService(database, "Test Pilot")
        await persistence.initialize()

        game_id = await persistence.start_game()
        engine = GameEngine(seed=1)
        engine.state.score = 30
        await persistence.complete_game(engine.state)

        scores = await persistence.leaderboard()
        assert game_id > 0
        assert [dict(score) for score in scores] == [
            {
                "name": "Test Pilot",
                "score": 30,
                "created_at": scores[0]["created_at"],
            }
        ]

        await persistence.close()

    asyncio.run(scenario())
