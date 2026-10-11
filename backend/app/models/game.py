from pydantic import BaseModel, ConfigDict

from backend.app.domain.game import Direction, GameState


class InputRequest(BaseModel):
    direction: Direction


class GameStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    width: int
    height: int
    snake: list[tuple[int, int]]
    food: tuple[int, int]
    direction: Direction
    score: int
    paused: bool
    game_over: bool

    @classmethod
    def from_domain(cls, state: GameState) -> GameStateResponse:
        return cls(
            width=state.board.width,
            height=state.board.height,
            snake=[(part.x, part.y) for part in state.snake.body],
            food=(state.food.x, state.food.y),
            direction=state.snake.direction,
            score=state.score,
            paused=state.paused,
            game_over=state.game_over,
        )
