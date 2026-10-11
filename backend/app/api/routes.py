"""Thin HTTP and WebSocket adapters for the Snakebite game service.

Learning note:
    Endpoints coordinate transport concerns only. All movement, collision, and
    scoring decisions remain in ``GameEngine``, which avoids maintaining two
    subtly different sets of rules for REST and WebSocket clients.
"""

import asyncio
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.domain.game import Direction
from backend.app.models.game import (
    GameStateResponse,
    InputRequest,
    ScoreResponse,
    StartGameRequest,
)
from backend.app.services.game_loop import GameLoopService, StateSignal
from backend.app.services.persistence import PersistenceService

router = APIRouter()
game_service = GameLoopService()
persistence_service: PersistenceService | None = None


def state_response() -> GameStateResponse:
    """Convert the engine's current state to its public representation."""

    return GameStateResponse.from_domain(
        game_service.state,
        started=game_service.started,
    )


def configure_persistence(service: PersistenceService) -> None:
    """Attach application storage after settings are loaded."""

    global persistence_service
    persistence_service = service


def require_persistence() -> PersistenceService:
    if persistence_service is None:
        raise RuntimeError("Persistence has not been configured")
    return persistence_service


@router.post("/game/start", response_model=GameStateResponse)
async def start_game(request: StartGameRequest | None = None) -> GameStateResponse:
    """Start a new game, optionally at a player-selected difficulty."""

    settings = request or StartGameRequest()
    await require_persistence().start_game(settings.player_name)
    await game_service.start_game(settings.difficulty, settings.plums)
    return state_response()


@router.get("/game/state", response_model=GameStateResponse)
def get_state() -> GameStateResponse:
    """Return the latest authoritative game state."""

    return state_response()


@router.post("/game/home", response_model=GameStateResponse)
async def return_home() -> GameStateResponse:
    """Stop gameplay and return the client to a fresh READY state."""

    await game_service.return_home()
    return state_response()


@router.post("/game/input", response_model=GameStateResponse)
async def input_direction(request: InputRequest) -> GameStateResponse:
    """Apply a player's direction request and return the resulting state."""

    await game_service.turn(request.direction)
    return state_response()


@router.post("/game/pause", response_model=GameStateResponse)
async def pause_game() -> GameStateResponse:
    """Pause the current game."""

    await game_service.pause()
    return state_response()


@router.post("/game/resume", response_model=GameStateResponse)
async def resume_game() -> GameStateResponse:
    """Resume the current game."""

    await game_service.resume()
    return state_response()


@router.get("/scores", response_model=list[ScoreResponse])
async def get_scores() -> list[ScoreResponse]:
    """Return the top completed scores."""

    rows = await require_persistence().leaderboard()
    return [ScoreResponse.model_validate(dict(row)) for row in rows]


@router.websocket("/ws/game")
async def game_socket(websocket: WebSocket) -> None:
    """Receive player input and stream authoritative state updates.

    The server sends the current state immediately, then broadcasts changes
    produced by input, lifecycle actions, and autonomous game ticks.
    """

    await websocket.accept()
    signals = game_service.subscribe()
    sender = asyncio.create_task(_send_updates(websocket, signals))
    try:
        await websocket.send_json(state_response().model_dump(mode="json"))
        while True:
            message = await websocket.receive_json()
            if not await _apply_socket_input(websocket, message):
                return
    except WebSocketDisconnect:
        return
    finally:
        game_service.unsubscribe(signals)
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender


async def _send_updates(websocket: WebSocket, signals: StateSignal) -> None:
    """Send the latest state whenever the game service signals a change."""

    while True:
        await signals.get()
        await websocket.send_json(state_response().model_dump(mode="json"))


async def _apply_socket_input(websocket: WebSocket, message: Any) -> bool:
    """Validate and apply one WebSocket direction message."""

    if not isinstance(message, dict) or not isinstance(message.get("direction"), str):
        await websocket.close(code=1008, reason="A direction message is required")
        return False

    try:
        direction = Direction(message["direction"])
    except ValueError:
        await websocket.close(code=1008, reason="Unknown direction")
        return False

    await game_service.turn(direction)
    return True
