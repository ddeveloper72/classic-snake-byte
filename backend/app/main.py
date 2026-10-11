"""FastAPI application composition root.

This module creates the web application and attaches transport adapters. It is
kept free of game rules so startup configuration can grow independently from
the domain.
"""

from fastapi import FastAPI

from backend.app.api.routes import router

app = FastAPI(title="Snakebite", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the application process is ready to receive requests."""

    return {"status": "ok"}
