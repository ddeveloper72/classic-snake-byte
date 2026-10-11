"""Thin HTTP and WebSocket adapters for the Snakebite game engine.

Learning note:
    Endpoints coordinate transport concerns only. All movement, collision, and
    scoring decisions remain in ``GameEngine``, which avoids maintaining two
    subtly different sets of rules for REST and WebSocket clients.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.domain.game import Direction, GameEngine
from backend.app.models.game import GameStateResponse, InputRequest

router = APIRouter()
engine = GameEngine(seed=42)


def state_response() -> GameStateResponse:
    """Convert the engine's current state to its public representation."""

    return GameStateResponse.from_domain(engine.state)


@router.post("/game/start", response_model=GameStateResponse)
def start_game() -> GameStateResponse:
    """Start a new game and return its initial state."""

    return GameStateResponse.from_domain(engine.reset())


@router.get("/game/state", response_model=GameStateResponse)
def get_state() -> GameStateResponse:
    """Return the latest authoritative game state."""

    return state_response()


@router.post("/game/input", response_model=GameStateResponse)
def input_direction(request: InputRequest) -> GameStateResponse:
    """Apply a player's direction request and return the resulting state."""

    return GameStateResponse.from_domain(engine.turn(request.direction))


@router.post("/game/pause", response_model=GameStateResponse)
def pause_game() -> GameStateResponse:
    """Pause the current game."""

    return GameStateResponse.from_domain(engine.pause())


@router.post("/game/resume", response_model=GameStateResponse)
def resume_game() -> GameStateResponse:
    """Resume the current game."""

    return GameStateResponse.from_domain(engine.resume())


@router.websocket("/ws/game")
async def game_socket(websocket: WebSocket) -> None:
    """Exchange direction or tick messages for authoritative state updates.

    The server sends the current state immediately after connecting and after
    every accepted client message. A future game-loop service will own ticks;
    accepting explicit tick messages keeps this first vertical slice testable.
    """

    await websocket.accept()
    try:
        await websocket.send_json(state_response().model_dump(mode="json"))
        while True:
            message = await websocket.receive_json()
            if "direction" in message:
                engine.turn(Direction(message["direction"]))
            elif message.get("action") == "tick":
                engine.tick()
            await websocket.send_json(state_response().model_dump(mode="json"))
    except (WebSocketDisconnect, ValueError):
        return
