"""Integration tests for the REST and WebSocket transport contracts."""

from collections.abc import Iterator

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Run each test with the FastAPI lifespan and game loop active."""

    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_start_and_input_endpoints(client: TestClient) -> None:
    start = client.post("/game/start")
    move = client.post("/game/input", json={"direction": "down"})

    assert start.status_code == 200
    assert start.json()["started"] is True
    assert move.status_code == 200
    assert move.json()["direction"] == "down"


def test_start_accepts_a_player_selected_difficulty(client: TestClient) -> None:
    response = client.post("/game/start", json={"difficulty": 5})

    assert response.status_code == 200
    assert response.json()["difficulty"] == 5


def test_start_defaults_to_the_gentlest_difficulty(client: TestClient) -> None:
    response = client.post("/game/start")

    assert response.status_code == 200
    assert response.json()["difficulty"] == 1


def test_start_rejects_an_out_of_range_difficulty(client: TestClient) -> None:
    response = client.post("/game/start", json={"difficulty": 9})

    assert response.status_code == 422


def test_home_stops_the_game_and_returns_a_fresh_ready_state(
    client: TestClient,
) -> None:
    client.post("/game/start", json={"difficulty": 5, "plums": 2})

    response = client.post("/game/home")
    state = response.json()

    assert response.status_code == 200
    assert state["started"] is False
    assert state["demo_mode"] is False
    assert state["game_over"] is False
    assert state["game_won"] is False
    assert state["score"] == 0
    assert state["level"] == 1


def test_first_level_state_reports_bar_and_initial_apple(client: TestClient) -> None:
    response = client.post("/game/start", json={"difficulty": 1})
    state = response.json()

    assert len(state["obstacles"]) > 1
    assert len({cell[1] for cell in state["obstacles"]}) == 1
    assert len(state["foods"]) == 1
    assert "food" not in state
    assert state["level_elapsed_seconds"] == 0
    assert state["speed_pressure_percent"] == 0


def test_websocket_returns_authoritative_state(client: TestClient) -> None:
    client.post("/game/start")
    client.post("/game/pause")
    with client.websocket_connect("/ws/game") as websocket:
        initial = websocket.receive_json()
        websocket.send_json({"direction": "up"})
        updated = websocket.receive_json()

    assert initial["score"] == 0
    assert updated["direction"] == "up"
    assert updated["snake"][0] == initial["snake"][0]


def test_websocket_receives_autonomous_game_ticks(client: TestClient) -> None:
    with client.websocket_connect("/ws/game") as websocket:
        websocket.receive_json()
        started = client.post("/game/start").json()
        websocket.receive_json()
        ticked = websocket.receive_json()

    assert ticked["snake"][0][0] == started["snake"][0][0] + 1
    assert ticked["snake"][0][1] == started["snake"][0][1]


def test_websocket_rejects_client_tick_messages(client: TestClient) -> None:
    with client.websocket_connect("/ws/game") as websocket:
        websocket.receive_json()
        websocket.send_json({"action": "tick"})
        with pytest.raises(WebSocketDisconnect) as disconnect:
            websocket.receive_json()

    assert disconnect.value.code == 1008
