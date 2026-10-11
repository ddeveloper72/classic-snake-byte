"""FastAPI application composition root.

This module creates the web application and attaches transport adapters. It is
kept free of game rules so startup configuration can grow independently from
the domain.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.routes import (
    configure_sessions,
    router,
)
from backend.app.config import Settings
from backend.app.repositories.database import Database
from backend.app.services.sessions import GameSessionManager

settings = Settings()
database = Database(settings.sqlite_path)
session_manager = GameSessionManager(database, settings.player_name)
configure_sessions(session_manager)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize shared storage and manage per-browser game sessions."""

    await database.connect()
    await database.initialize()
    await session_manager.start()
    try:
        yield
    finally:
        await session_manager.stop()
        await database.close()


app = FastAPI(title="Snakebite", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the application process is ready to receive requests."""

    return {"status": "ok"}
