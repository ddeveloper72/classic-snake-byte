from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.domain.game import Direction, GameEngine
from backend.app.models.game import GameStateResponse, InputRequest

router = APIRouter()
engine = GameEngine(seed=42)


def state_response() -> GameStateResponse:
    return GameStateResponse.from_domain(engine.state)


@router.post("/game/start", response_model=GameStateResponse)
def start_game() -> GameStateResponse:
    return GameStateResponse.from_domain(engine.reset())


@router.get("/game/state", response_model=GameStateResponse)
def get_state() -> GameStateResponse:
    return state_response()


@router.post("/game/input", response_model=GameStateResponse)
def input_direction(request: InputRequest) -> GameStateResponse:
    return GameStateResponse.from_domain(engine.turn(request.direction))


@router.post("/game/pause", response_model=GameStateResponse)
def pause_game() -> GameStateResponse:
    return GameStateResponse.from_domain(engine.pause())


@router.post("/game/resume", response_model=GameStateResponse)
def resume_game() -> GameStateResponse:
    return GameStateResponse.from_domain(engine.resume())


@router.websocket("/ws/game")
async def game_socket(websocket: WebSocket) -> None:
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
