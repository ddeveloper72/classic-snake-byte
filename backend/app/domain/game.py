from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from random import Random


@dataclass(frozen=True, slots=True)
class Position:
    x: int
    y: int


class Direction(StrEnum):
    UP = "up"
    RIGHT = "right"
    DOWN = "down"
    LEFT = "left"

    @property
    def delta(self) -> tuple[int, int]:
        return {
            Direction.UP: (0, -1),
            Direction.RIGHT: (1, 0),
            Direction.DOWN: (0, 1),
            Direction.LEFT: (-1, 0),
        }[self]

    @property
    def opposite(self) -> Direction:
        return {
            Direction.UP: Direction.DOWN,
            Direction.RIGHT: Direction.LEFT,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
        }[self]


@dataclass(frozen=True, slots=True)
class GameBoard:
    width: int = 24
    height: int = 16

    def contains(self, position: Position) -> bool:
        return 0 <= position.x < self.width and 0 <= position.y < self.height


@dataclass(slots=True)
class Snake:
    body: list[Position]
    direction: Direction = Direction.RIGHT

    @property
    def head(self) -> Position:
        return self.body[0]

    def next_head(self) -> Position:
        dx, dy = self.direction.delta
        return Position(self.head.x + dx, self.head.y + dy)

    def turn(self, direction: Direction) -> None:
        if len(self.body) > 1 and direction == self.direction.opposite:
            return
        self.direction = direction


@dataclass(slots=True)
class GameState:
    board: GameBoard
    snake: Snake
    food: Position
    score: int = 0
    paused: bool = False
    game_over: bool = False


class GameEngine:
    """Server-authoritative game rules, independent of HTTP and persistence."""

    def __init__(self, board: GameBoard | None = None, seed: int | None = None):
        self._board = board or GameBoard()
        self._random = Random(seed)
        self.state = self._new_state()

    def _new_state(self) -> GameState:
        center = Position(self._board.width // 2, self._board.height // 2)
        snake = Snake(
            [center, Position(center.x - 1, center.y), Position(center.x - 2, center.y)]
        )
        state = GameState(self._board, snake, center)
        state.food = self._spawn_food(state)
        return state

    def reset(self) -> GameState:
        self.state = self._new_state()
        return self.state

    def turn(self, direction: Direction) -> GameState:
        if not self.state.game_over:
            self.state.snake.turn(direction)
        return self.state

    def pause(self) -> GameState:
        if not self.state.game_over:
            self.state.paused = True
        return self.state

    def resume(self) -> GameState:
        if not self.state.game_over:
            self.state.paused = False
        return self.state

    def tick(self) -> GameState:
        if self.state.paused or self.state.game_over:
            return self.state

        next_head = self.state.snake.next_head()
        eats_food = next_head == self.state.food
        body_to_check = (
            self.state.snake.body if eats_food else self.state.snake.body[:-1]
        )
        if not self.state.board.contains(next_head) or next_head in body_to_check:
            self.state.game_over = True
            return self.state

        self.state.snake.body.insert(0, next_head)
        if eats_food:
            self.state.score += 10
            self.state.food = self._spawn_food(self.state)
        else:
            self.state.snake.body.pop()
        return self.state

    def _spawn_food(self, state: GameState) -> Position:
        available = [
            Position(x, y)
            for y in range(state.board.height)
            for x in range(state.board.width)
            if Position(x, y) not in state.snake.body
        ]
        if not available:
            return state.snake.head
        return self._random.choice(available)
