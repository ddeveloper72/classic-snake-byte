"""FastAPI application composition root.

This module creates the web application and attaches transport adapters. It is
kept free of game rules so startup configuration can grow independently from
the domain.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.routes import game_service, router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start and stop the autonomous game loop with the web application."""

    await game_service.start_loop()
    try:
        yield
    finally:
        await game_service.stop_loop()


app = FastAPI(title="Snakebite", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the application process is ready to receive requests."""

    return {"status": "ok"}
