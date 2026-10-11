"""Validated request and response contracts exposed by the game API.

Learning note:
    API schemas are separate from domain dataclasses so external contracts can
    evolve without adding web-framework concerns to the game engine. Pydantic
    also validates input and generates the OpenAPI schema used by FastAPI.
"""

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.game import (
    MAX_DIFFICULTY,
    MAX_PLUMS,
    MIN_DIFFICULTY,
    MIN_PLUMS,
    Direction,
    GameState,
)


class ScoreResponse(BaseModel):
    """A completed score suitable for the public leaderboard."""

    name: str
    score: int
    created_at: str


class InputRequest(BaseModel):
    """A player request to change the snake's direction."""

    direction: Direction


class StartGameRequest(BaseModel):
    """A player request to start a game at a chosen pace."""

    difficulty: int = Field(
        default=MIN_DIFFICULTY,
        ge=MIN_DIFFICULTY,
        le=MAX_DIFFICULTY,
        description="1 is the gentlest pace and 5 matches the 1981 original.",
    )
    plums: int = Field(
        default=MIN_PLUMS,
        ge=MIN_PLUMS,
        le=MAX_PLUMS,
        description="Perilous plums that bounce around the board, 0 to 2.",
    )


class GameStateResponse(BaseModel):
    """The JSON-safe representation of the current game state."""

    model_config = ConfigDict(from_attributes=True)

    width: int
    height: int
    snake: list[tuple[int, int]]
    foods: list[tuple[int, int]]
    obstacles: list[tuple[int, int]]
    plums: list[tuple[int, int]]
    plum_bounced: bool
    direction: Direction
    score: int
    level: int
    # Apples left before the exit door unlocks; the door is the only route to
    # the next level.
    apples_remaining: int
    door_open: bool
    door_x: int
    level_cleared: bool
    level_elapsed_seconds: float
    speed_pressure_percent: int
    difficulty: int
    started: bool
    paused: bool
    game_over: bool
    game_won: bool
    demo_mode: bool

    @classmethod
    def from_domain(cls, state: GameState, *, started: bool) -> GameStateResponse:
        """Translate internal domain objects into the public API contract."""

        return cls(
            width=state.board.width,
            height=state.board.height,
            snake=[(part.x, part.y) for part in state.snake.body],
            foods=[(food.x, food.y) for food in state.foods],
            # Sorted so repeated snapshots of one layout are byte-identical.
            obstacles=sorted((cell.x, cell.y) for cell in state.obstacles),
            # Plum order is preserved rather than sorted so a client can keep
            # animating the same plum between frames.
            plums=[(plum.position.x, plum.position.y) for plum in state.plums],
            plum_bounced=state.plum_bounced,
            direction=state.snake.direction,
            score=state.score,
            level=state.level,
            apples_remaining=state.apples_remaining,
            door_open=state.door_open,
            door_x=state.door_x,
            level_cleared=state.level_cleared,
            level_elapsed_seconds=state.level_elapsed_seconds,
            speed_pressure_percent=state.speed_pressure_step * 5,
            difficulty=state.difficulty,
            started=started,
            paused=state.paused,
            game_over=state.game_over,
            game_won=state.game_won,
            demo_mode=state.demo_mode,
        )
