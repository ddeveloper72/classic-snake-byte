"""Framework-independent rules and state for a game of Snakebite.

The domain module deliberately imports neither FastAPI nor Pydantic. Keeping the
rules independent from delivery and persistence concerns means the same engine
can support a web API, a command-line client, or automated simulations.

Learning note:
    Dataclasses make the game's small domain objects explicit and type-safe
    without the validation and serialization behavior needed at the API edge.
    Immutable value objects such as ``Position`` and ``GameBoard`` are safe to
    compare and share, while ``Snake`` and ``GameState`` remain mutable because
    they represent state that changes on every game tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from random import Random


@dataclass(frozen=True, slots=True)
class Position:
    """A zero-based coordinate on the game board."""

    x: int
    y: int


class Direction(StrEnum):
    """A cardinal movement direction accepted by the engine and API."""

    UP = "up"
    RIGHT = "right"
    DOWN = "down"
    LEFT = "left"

    @property
    def delta(self) -> tuple[int, int]:
        """Return the x/y offset used to move one board cell."""

        return {
            Direction.UP: (0, -1),
            Direction.RIGHT: (1, 0),
            Direction.DOWN: (0, 1),
            Direction.LEFT: (-1, 0),
        }[self]

    @property
    def opposite(self) -> Direction:
        """Return the direction that would immediately reverse the snake."""

        return {
            Direction.UP: Direction.DOWN,
            Direction.RIGHT: Direction.LEFT,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
        }[self]


@dataclass(frozen=True, slots=True)
class GameBoard:
    """The immutable rectangular boundary in which gameplay occurs."""

    width: int = 24
    height: int = 16

    def contains(self, position: Position) -> bool:
        """Return whether a position is inside the playable board."""

        return 0 <= position.x < self.width and 0 <= position.y < self.height


@dataclass(slots=True)
class Snake:
    """The ordered snake body and its current direction of travel.

    ``body[0]`` is always the head and the final item is always the tail.
    """

    body: list[Position]
    direction: Direction = Direction.RIGHT

    @property
    def head(self) -> Position:
        """Return the snake's leading body segment."""

        return self.body[0]

    def next_head(self) -> Position:
        """Calculate, but do not apply, the next head position."""

        dx, dy = self.direction.delta
        return Position(self.head.x + dx, self.head.y + dy)

    def turn(self, direction: Direction) -> None:
        """Change direction unless doing so would reverse into the body."""

        if len(self.body) > 1 and direction == self.direction.opposite:
            return
        self.direction = direction


@dataclass(slots=True)
class GameState:
    """A complete snapshot of one active game's mutable state."""

    board: GameBoard
    snake: Snake
    food: Position
    score: int = 0
    level: int = 1
    paused: bool = False
    game_over: bool = False


class GameEngine:
    """Advance and control server-authoritative Snakebite game state.

    Args:
        board: Optional board dimensions, useful for alternate modes and tests.
        seed: Optional random seed for reproducible food placement in tests.

    The engine owns exactly one game state. Public methods return that state so
    adapters can serialize the result without duplicating game rules.
    """

    def __init__(
        self,
        board: GameBoard | None = None,
        seed: int | None = None,
        *,
        base_tick_interval: float = 0.16,
    ):
        self._board = board or GameBoard()
        self._random = Random(seed)
        self._base_tick_interval = base_tick_interval
        self.state = self._new_state()

    @property
    def level(self) -> int:
        """Return the current game difficulty band based on score."""

        return max(1, self.state.score // 40 + 1)

    @property
    def tick_interval(self) -> float:
        """Return the active speed for this level."""

        level = self.level
        return max(0.08, self._base_tick_interval - (level - 1) * 0.015)

    def _new_state(self) -> GameState:
        """Build the standard three-segment starting state."""

        center = Position(self._board.width // 2, self._board.height // 2)
        snake = Snake(
            [center, Position(center.x - 1, center.y), Position(center.x - 2, center.y)]
        )
        state = GameState(self._board, snake, center, level=1)
        state.food = self._spawn_food(state)
        return state

    def reset(self) -> GameState:
        """Replace the current game with a fresh, active game."""

        self.state = self._new_state()
        return self.state

    def turn(self, direction: Direction) -> GameState:
        """Request a new direction unless the game has ended."""

        if not self.state.game_over:
            self.state.snake.turn(direction)
        return self.state

    def pause(self) -> GameState:
        """Pause an active game without changing its board state."""

        if not self.state.game_over:
            self.state.paused = True
        return self.state

    def resume(self) -> GameState:
        """Resume a paused game unless that game has ended."""

        if not self.state.game_over:
            self.state.paused = False
        return self.state

    def tick(self) -> GameState:
        """Advance the game by one movement interval.

        A tick moves the head, resolves collisions, grows the snake when food is
        eaten, updates the score, and places the next food item.
        """

        if self.state.paused or self.state.game_over:
            return self.state

        next_head = self.state.snake.next_head()
        eats_food = next_head == self.state.food
        # On a normal move the tail vacates its cell, so moving into it is safe.
        body_to_check = (
            self.state.snake.body if eats_food else self.state.snake.body[:-1]
        )
        if not self.state.board.contains(next_head) or next_head in body_to_check:
            self.state.game_over = True
            return self.state

        self.state.snake.body.insert(0, next_head)
        if eats_food:
            self.state.score += 10
            self.state.level = self.level
            self.state.food = self._spawn_food(self.state)
        else:
            self.state.snake.body.pop()
        self.state.level = self.level
        return self.state

    def _spawn_food(self, state: GameState) -> Position:
        """Choose an unoccupied cell, or the head when the board is full."""

        # Constructing valid cells first guarantees food never appears in the snake.
        available = [
            Position(x, y)
            for y in range(state.board.height)
            for x in range(state.board.width)
            if Position(x, y) not in state.snake.body
        ]
        if not available:
            return state.snake.head
        return self._random.choice(available)
