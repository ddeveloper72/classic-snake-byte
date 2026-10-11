"""Integration tests for the REST and WebSocket transport contracts."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_start_and_input_endpoints() -> None:
    start = client.post("/game/start")
    move = client.post("/game/input", json={"direction": "down"})

    assert start.status_code == 200
    assert move.status_code == 200
    assert move.json()["direction"] == "down"


def test_websocket_returns_authoritative_state() -> None:
    client.post("/game/start")
    with client.websocket_connect("/ws/game") as websocket:
        initial = websocket.receive_json()
        websocket.send_json({"direction": "up"})
        updated = websocket.receive_json()

    assert initial["score"] == 0
    assert updated["direction"] == "up"
    assert updated["snake"][0] == initial["snake"][0]
