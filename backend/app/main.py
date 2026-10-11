"""FastAPI application composition root.

This module creates the web application and attaches transport adapters. It is
kept free of game rules so startup configuration can grow independently from
the domain.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.routes import (
    configure_persistence,
    game_service,
    router,
)
from backend.app.config import Settings
from backend.app.domain.game import GameState
from backend.app.repositories.database import Database
from backend.app.services.persistence import PersistenceService

settings = Settings()
database = Database(settings.sqlite_path)
persistence_service = PersistenceService(database, settings.player_name)
configure_persistence(persistence_service)


async def persist_game_over(state: GameState) -> None:
    await persistence_service.complete_game(state)


game_service.set_game_over_handler(persist_game_over)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start and stop the autonomous game loop with the web application."""

    await persistence_service.initialize()
    await game_service.start_loop()
    try:
        yield
    finally:
        await game_service.stop_loop()
        await persistence_service.close()


app = FastAPI(title="Snakebite", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the application process is ready to receive requests."""

    return {"status": "ok"}
