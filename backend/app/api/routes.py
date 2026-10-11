"""HTTP and WebSocket adapters for independently owned browser game sessions."""

import asyncio
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from starlette.websockets import WebSocketDisconnect

from backend.app.domain.game import Direction
from backend.app.models.game import (
    GameStateResponse,
    InputRequest,
    ScoreResponse,
    StartGameRequest,
)
from backend.app.services.game_loop import StateSignal
from backend.app.services.sessions import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    GameSession,
    GameSessionManager,
    SessionCapacityError,
)

router = APIRouter()
session_manager: GameSessionManager | None = None


def configure_sessions(manager: GameSessionManager) -> None:
    """Attach the application-owned session manager."""

    global session_manager
    session_manager = manager


def require_session_manager() -> GameSessionManager:
    if session_manager is None:
        raise RuntimeError("Game sessions have not been configured")
    return session_manager


async def require_game_session(request: Request, response: Response) -> GameSession:
    """Resolve the unexposed browser credential from its HttpOnly cookie."""

    try:
        session = await require_session_manager().get_or_create(
            request.cookies.get(SESSION_COOKIE_NAME),
        )
    except SessionCapacityError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    host = request.url.hostname or ""
    secure = request.url.scheme == "https" or host not in {
        "localhost",
        "127.0.0.1",
        "::1",
        "testserver",
    }
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.token,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        secure=secure,
        httponly=True,
        samesite="strict",
    )
    return session


def state_response(session: GameSession) -> GameStateResponse:
    """Convert this session's authoritative state to its public representation."""

    return GameStateResponse.from_domain(
        session.game_service.state,
        started=session.game_service.started,
    )


@router.post("/session")
async def create_browser_session(
    _: Annotated[GameSession, Depends(require_game_session)],
) -> dict[str, bool]:
    """Establish a browser session without returning its credential to JavaScript."""

    return {"ready": True}


@router.post("/game/start", response_model=GameStateResponse)
async def start_game(
    session: Annotated[GameSession, Depends(require_game_session)],
    request: StartGameRequest | None = None,
) -> GameStateResponse:
    """Start a game belonging only to the authenticated browser session."""

    settings = request or StartGameRequest()
    async with session.action_lock:
        await session.persistence.start_game(settings.player_name)
        await session.game_service.start_game(settings.difficulty, settings.plums)
    return state_response(session)


@router.get("/game/state", response_model=GameStateResponse)
async def get_state(
    session: Annotated[GameSession, Depends(require_game_session)],
) -> GameStateResponse:
    return state_response(session)


@router.post("/game/home", response_model=GameStateResponse)
async def return_home(
    session: Annotated[GameSession, Depends(require_game_session)],
) -> GameStateResponse:
    """Stop this session's game and expose its fresh, inactive board."""

    await session.game_service.return_home()
    return state_response(session)


@router.post("/game/input", response_model=GameStateResponse)
async def input_direction(
    request: InputRequest,
    session: Annotated[GameSession, Depends(require_game_session)],
) -> GameStateResponse:
    await session.game_service.turn(request.direction)
    return state_response(session)


@router.post("/game/pause", response_model=GameStateResponse)
async def pause_game(
    session: Annotated[GameSession, Depends(require_game_session)],
) -> GameStateResponse:
    await session.game_service.pause()
    return state_response(session)


@router.post("/game/resume", response_model=GameStateResponse)
async def resume_game(
    session: Annotated[GameSession, Depends(require_game_session)],
) -> GameStateResponse:
    await session.game_service.resume()
    return state_response(session)


@router.get("/scores", response_model=list[ScoreResponse])
async def get_scores() -> list[ScoreResponse]:
    """Return the shared public winners leaderboard."""

    manager = require_session_manager()
    rows = await manager.leaderboard()
    return [ScoreResponse.model_validate(dict(row)) for row in rows]


@router.websocket("/ws/game")
async def game_socket(websocket: WebSocket) -> None:
    """Stream and accept input only for the browser's cookie-owned game."""

    session = await require_session_manager().connect(
        websocket.cookies.get(SESSION_COOKIE_NAME),
    )
    if session is None:
        await websocket.close(code=4401, reason="A valid browser session is required")
        return

    await websocket.accept()
    signals = session.game_service.subscribe()
    sender = asyncio.create_task(_send_updates(websocket, signals, session))
    try:
        await websocket.send_json(state_response(session).model_dump(mode="json"))
        while True:
            message = await websocket.receive_json()
            if not await _apply_socket_input(websocket, message, session):
                return
    except WebSocketDisconnect:
        return
    finally:
        session.game_service.unsubscribe(signals)
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender
        await require_session_manager().disconnect(session)


async def _send_updates(
    websocket: WebSocket,
    signals: StateSignal,
    session: GameSession,
) -> None:
    """Send state changes from only the owning game session."""

    while True:
        await signals.get()
        await websocket.send_json(state_response(session).model_dump(mode="json"))
        require_session_manager().touch(session)


async def _apply_socket_input(
    websocket: WebSocket,
    message: Any,
    session: GameSession,
) -> bool:
    """Validate and apply one direction request to the owning game."""

    if not isinstance(message, dict) or not isinstance(message.get("direction"), str):
        await websocket.close(code=1008, reason="A direction message is required")
        return False

    try:
        direction = Direction(message["direction"])
    except ValueError:
        await websocket.close(code=1008, reason="Unknown direction")
        return False

    await session.game_service.turn(direction)
    require_session_manager().touch(session)
    return True
