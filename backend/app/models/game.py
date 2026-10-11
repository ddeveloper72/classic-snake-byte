"""Validated request and response contracts exposed by the game API.

Learning note:
    API schemas are separate from domain dataclasses so external contracts can
    evolve without adding web-framework concerns to the game engine. Pydantic
    also validates input and generates the OpenAPI schema used by FastAPI.
"""

from pydantic import BaseModel, ConfigDict

from backend.app.domain.game import Direction, GameState


class InputRequest(BaseModel):
    """A player request to change the snake's direction."""

    direction: Direction


class GameStateResponse(BaseModel):
    """The JSON-safe representation of the current game state."""

    model_config = ConfigDict(from_attributes=True)

    width: int
    height: int
    snake: list[tuple[int, int]]
    food: tuple[int, int]
    direction: Direction
    score: int
    started: bool
    paused: bool
    game_over: bool

    @classmethod
    def from_domain(cls, state: GameState, *, started: bool) -> GameStateResponse:
        """Translate internal domain objects into the public API contract."""

        return cls(
            width=state.board.width,
            height=state.board.height,
            snake=[(part.x, part.y) for part in state.snake.body],
            food=(state.food.x, state.food.y),
            direction=state.snake.direction,
            score=state.score,
            started=started,
            paused=state.paused,
            game_over=state.game_over,
        )
