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

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from random import Random

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5

# The 1981 original asked "HOW MANY PLUMS?" before every game and accepted
# zero, one, or two. Perilous plums bounce around the board and kill the snake
# on contact with its head, so the count is a second difficulty dial.
MIN_PLUMS = 0
MAX_PLUMS = 2

# Learning note:
#     Difficulty is a player-chosen accessibility setting rather than a hidden
#     constant. Setting 1 moves roughly three cells per second so players who
#     need more reaction time can still finish a board, while setting 5 keeps
#     the frantic pace of the 1981 original.
SECONDS_PER_CELL: dict[int, float] = {
    1: 0.40,
    2: 0.32,
    3: 0.25,
    4: 0.19,
    5: 0.13,
}

# Levels speed up gently and never fall below this share of the chosen pace, so
# a slow difficulty stays playable even deep into a long game.
LEVEL_SPEED_STEP = 0.94
MIN_LEVEL_SPEED_RATIO = 0.6

# Taking too long on one board adds gentle arcade pressure without overriding
# the player's chosen base difficulty. Five 20-second stages produce the
# selected 25% cap, and the level timer resets only after using the exit door.
PRESSURE_INTERVAL_SECONDS = 20.0
PRESSURE_SPEED_STEP = 0.05
MAX_PRESSURE_STEPS = 5

# Learning note:
#     Fifteen apples let each maze develop rather than ending after only a few
#     turns. More apples share the board as a level progresses, while the total
#     remains fixed and visible in the APPLES counter.
APPLES_PER_LEVEL = 15
APPLES_PER_SPAWN_STEP = 3
MAX_VISIBLE_APPLES = 5
MAZE_COUNT = 10

# Points awarded for one apple, kept here so the score and the apple counter
# can never drift apart.
POINTS_PER_APPLE = 10


def clamp_difficulty(difficulty: int) -> int:
    """Return a difficulty forced into the supported 1-5 range."""

    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, difficulty))


def clamp_plums(plums: int) -> int:
    """Return a plum count forced into the supported 0-2 range."""

    return max(MIN_PLUMS, min(MAX_PLUMS, plums))


def growth_for_apple(apple_number: int) -> int:
    """Return the body cells awarded by an apple numbered 1 through 15."""

    if apple_number <= 3:
        return 1
    if apple_number <= 7:
        return 2
    if apple_number <= 11:
        return 3
    return 4


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


def spawn_corridor(board: GameBoard) -> frozenset[Position]:
    """Return the lane the snake starts in and first travels along.

    Keeping this lane clear guarantees a new game or a level change can never
    drop a wall onto the snake or directly in front of it.
    """

    center_y = board.height - 2
    first_segment_x = board.width // 2 - 2
    return frozenset(Position(x, center_y) for x in range(first_segment_x, board.width))


def door_column(board: GameBoard, level: int) -> int:
    """Return the x position of the exit door in the top wall for a level.

    Learning note:
        The door moves from level to level so the run to the exit is a fresh
        navigation problem each time. It is derived from the level rather than
        drawn at random so a replayed level always behaves identically, which
        keeps the engine deterministic and testable.
    """

    usable = max(1, board.width - 4)
    return 2 + (level * 7) % usable


def build_obstacles(board: GameBoard, level: int) -> frozenset[Position]:
    """Return one of ten intentional maze lessons.

    The catalogue repeats after level 10, allowing an endless game without
    inventing progressively less readable walls. Level 8 is a two-door
    training room: it teaches entering, turning inside, and leaving a chamber
    before level 10 removes the second escape route.
    """

    pattern = (max(1, level) - 1) % MAZE_COUNT + 1
    cells: set[Position] = set()
    center_x = board.width // 2
    center_y = board.height // 2

    def horizontal(y: int, start: int, stop: int, gaps: set[int] | None = None) -> None:
        cells.update(
            Position(x, y) for x in range(start, stop + 1) if x not in (gaps or set())
        )

    def vertical(x: int, start: int, stop: int, gaps: set[int] | None = None) -> None:
        cells.update(
            Position(x, y) for y in range(start, stop + 1) if y not in (gaps or set())
        )

    if pattern == 1:
        horizontal(center_y, 5, board.width - 6)
    elif pattern == 2:
        horizontal(center_y, 3, board.width - 4, {center_x, center_x + 1})
    elif pattern == 3:
        for x in (5, center_x, board.width - 6):
            vertical(x, 3, board.height - 5)
    elif pattern == 4:
        vertical(6, 3, board.height - 5)
        for y in (3, center_y, board.height - 5):
            horizontal(y, 6, board.width - 7)
    elif pattern == 5:
        horizontal(center_y, 5, board.width - 6)
        vertical(center_x, 2, board.height - 5)
    elif pattern == 6:
        for x in (4, center_x, board.width - 5):
            vertical(x, 3, board.height - 5)
        horizontal(center_y, 4, center_x)
        horizontal(center_y, center_x, board.width - 5)
    elif pattern == 7:
        horizontal(center_y, 0, center_x - 3)
        horizontal(center_y, center_x + 3, board.width - 1)
        vertical(center_x, 2, board.height - 5)
    elif pattern == 8:
        # The "practice room" has a bottom entrance, a side escape, and a
        # baffle that makes the player turn after crossing the threshold.
        left, right, top, bottom = 6, board.width - 7, 3, board.height - 5
        horizontal(top, left, right)
        horizontal(bottom, left, right, {center_x, center_x + 1})
        vertical(left, top, bottom)
        vertical(right, top, bottom, {center_y - 1, center_y})
        vertical(center_x - 2, top + 3, bottom - 2)
    elif pattern == 9:
        for x in (board.width // 3, board.width * 2 // 3):
            vertical(x, 1, board.height - 3, set(range(2, board.height - 3, 2)))
    else:
        # A single-door room: enter through the bottom, turn inside it, then
        # return through the same opening.
        left, right, top, bottom = 7, board.width - 8, 3, board.height - 5
        horizontal(top, left, right)
        horizontal(bottom, left, right, {center_x})
        vertical(left, top, bottom)
        vertical(right, top, bottom)

    return frozenset(cells) - spawn_corridor(board)


@dataclass(slots=True)
class Plum:
    """A perilous plum that bounces diagonally around the board.

    Learning note:
        The original's plums travel on a diagonal and rebound off walls, maze
        pieces, and the snake's own body, which is why they feel like a loose
        pinball rather than a chasing enemy. Only the snake's head is lethal to
        touch, so the body can be used as a shield to deflect a plum away.
    """

    position: Position
    dx: int = 1
    dy: int = 1

    def reflected(self, *, flip_x: bool, flip_y: bool) -> Plum:
        """Return this plum with either axis of travel reversed."""

        return Plum(
            self.position,
            -self.dx if flip_x else self.dx,
            -self.dy if flip_y else self.dy,
        )

    def advanced(self) -> Plum:
        """Return this plum moved one cell along its current heading."""

        return Plum(
            Position(self.position.x + self.dx, self.position.y + self.dy),
            self.dx,
            self.dy,
        )


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
    foods: list[Position]
    score: int = 0
    level: int = 1
    # Apples still to eat before the exit door unlocks. The door is the only
    # way to reach the next level, so this counter gates progress.
    apples_remaining: int = APPLES_PER_LEVEL
    # Additional tail cells earned by an apple appear over future ticks. This
    # avoids overlapping duplicate segments when one apple awards 2-4 cells.
    growth_pending: int = 0
    level_elapsed_seconds: float = 0.0
    speed_pressure_step: int = 0
    door_open: bool = False
    door_x: int = 0
    difficulty: int = MIN_DIFFICULTY
    obstacles: frozenset[Position] = field(default_factory=frozenset)
    plums: list[Plum] = field(default_factory=list)
    # Transient, cleared at the start of every tick, so adapters can play a
    # rebound sound without tracking plum headings between snapshots.
    plum_bounced: bool = False
    # Transient, set on the tick the snake threads the exit door.
    level_cleared: bool = False
    paused: bool = False
    game_over: bool = False
    demo_mode: bool = False


class GameEngine:
    """Advance and control server-authoritative Snakebite game state.

    Args:
        board: Optional board dimensions, useful for alternate modes and tests.
        seed: Optional random seed for reproducible food placement in tests.
        difficulty: The player-selected pace, from 1 (gentlest) to 5 (original).
        plums: How many perilous plums bounce around the board, from 0 to 2.

    The engine owns exactly one game state. Public methods return that state so
    adapters can serialize the result without duplicating game rules.
    """

    def __init__(
        self,
        board: GameBoard | None = None,
        seed: int | None = None,
        *,
        difficulty: int = MIN_DIFFICULTY,
        plums: int = MIN_PLUMS,
    ):
        self._board = board or GameBoard()
        self._random = Random(seed)
        self._difficulty = clamp_difficulty(difficulty)
        self._plums = clamp_plums(plums)
        self.state = self._new_state()

    @property
    def difficulty(self) -> int:
        """Return the player-selected pace setting."""

        return self._difficulty

    @property
    def plums(self) -> int:
        """Return how many perilous plums each new game starts with."""

        return self._plums

    @property
    def level(self) -> int:
        """Return the current level.

        Learning note:
            The level is authoritative state rather than a function of the
            score, because it now only rises when the snake leaves through the
            exit door. Deriving it from the score would let a player skip the
            door simply by eating.
        """

        return self.state.level

    @property
    def tick_interval(self) -> float:
        """Return seconds per cell after level and time-pressure acceleration."""

        base = SECONDS_PER_CELL[self._difficulty]
        ramped = base * (LEVEL_SPEED_STEP ** (self.level - 1))
        level_interval = max(base * MIN_LEVEL_SPEED_RATIO, ramped)
        pressure_multiplier = (
            1.0 + self.state.speed_pressure_step * PRESSURE_SPEED_STEP
        )
        return level_interval / pressure_multiplier

    def advance_level_time(self, seconds: float) -> GameState:
        """Add active player time and update the current pressure stage.

        Paused, completed, and demonstration games do not accumulate pressure.
        Keeping time advancement explicit makes the rule deterministic in
        tests and prevents server scheduling delays from unfairly speeding up
        the snake.
        """

        if seconds < 0:
            raise ValueError("seconds cannot be negative")
        if (
            self.state.paused
            or self.state.game_over
            or self.state.demo_mode
            or self.state.door_open
        ):
            return self.state

        self.state.level_elapsed_seconds += seconds
        self.state.speed_pressure_step = min(
            MAX_PRESSURE_STEPS,
            int(self.state.level_elapsed_seconds // PRESSURE_INTERVAL_SECONDS),
        )
        return self.state

    def set_difficulty(self, difficulty: int) -> GameState:
        """Change the pace setting, applying it to the current state."""

        self._difficulty = clamp_difficulty(difficulty)
        self.state.difficulty = self._difficulty
        return self.state

    def set_plums(self, plums: int) -> GameState:
        """Choose how many perilous plums the next game starts with."""

        self._plums = clamp_plums(plums)
        return self.state

    def _new_state(self) -> GameState:
        """Build the standard three-segment starting state."""

        center = Position(self._board.width // 2, self._board.height - 2)
        snake = Snake(
            [center, Position(center.x - 1, center.y), Position(center.x - 2, center.y)]
        )
        state = GameState(
            self._board,
            snake,
            [],
            level=1,
            door_x=door_column(self._board, 1),
            difficulty=self._difficulty,
            obstacles=build_obstacles(self._board, 1),
            demo_mode=False,
        )
        self._replenish_foods(state)
        state.plums = self._spawn_plums(state, self._plums)
        return state

    def _spawn_plums(self, state: GameState, count: int) -> list[Plum]:
        """Place plums on free cells well clear of the snake's starting lane."""

        corridor = spawn_corridor(state.board)
        taken = {*state.snake.body, *state.foods}
        plums: list[Plum] = []
        for _ in range(clamp_plums(count)):
            available = [
                Position(x, y)
                for y in range(state.board.height)
                for x in range(state.board.width)
                if Position(x, y) not in state.obstacles
                and Position(x, y) not in corridor
                and Position(x, y) not in taken
            ]
            if not available:
                break
            start = self._random.choice(available)
            taken.add(start)
            plums.append(
                Plum(
                    start,
                    self._random.choice((-1, 1)),
                    self._random.choice((-1, 1)),
                )
            )
        return plums

    def _apply_level_layout(self) -> None:
        """Swap in the current level's walls without burying the live snake."""

        layout = build_obstacles(self.state.board, self.state.level)
        # A level can change mid-game, so never place a wall on the snake.
        self.state.obstacles = layout - set(self.state.snake.body)
        self.state.foods = [
            food for food in self.state.foods if food not in self.state.obstacles
        ]
        self._replenish_foods(self.state)
        # A plum caught inside a brand-new wall would be stuck there forever,
        # so any trapped plum is re-released onto open ground.
        if any(plum.position in self.state.obstacles for plum in self.state.plums):
            survivors = [
                plum
                for plum in self.state.plums
                if plum.position not in self.state.obstacles
            ]
            trapped = len(self.state.plums) - len(survivors)
            self.state.plums = survivors + self._spawn_plums(self.state, trapped)

    def set_demo_level(self, level: int) -> GameState:
        """Prepare a fresh board and score for a demo session at a chosen level."""

        target_level = max(1, min(level, MAZE_COUNT))
        self.state = self._new_state()
        self.state.score = (target_level - 1) * APPLES_PER_LEVEL * POINTS_PER_APPLE
        self.state.level = target_level
        self.state.door_x = door_column(self._board, target_level)
        self.state.demo_mode = True
        self._apply_level_layout()
        self.state.foods.clear()
        self._replenish_foods(self.state)
        # Demos re-place plums after the level walls exist so an attract-mode
        # run shows the same hazards a player would face at that level.
        self.state.plums = self._spawn_plums(self.state, self._plums)
        return self.state

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

        self.state.plum_bounced = False
        self.state.level_cleared = False

        next_head = self.state.snake.next_head()

        # The exit door is a gap in the top wall, so leaving the board through
        # that one column clears the level instead of killing the snake.
        if (
            self.state.door_open
            and next_head.y < 0
            and next_head.x == self.state.door_x
        ):
            self._advance_level()
            return self.state

        eats_food = next_head in self.state.foods
        # On a normal move the tail vacates its cell, so moving into it is safe.
        body_to_check = (
            self.state.snake.body
            if eats_food or self.state.growth_pending > 0
            else self.state.snake.body[:-1]
        )
        if (
            not self.state.board.contains(next_head)
            or next_head in body_to_check
            or next_head in self.state.obstacles
        ):
            self.state.game_over = True
            return self.state

        # Steering into a plum is just as fatal as being struck by one.
        if any(plum.position == next_head for plum in self.state.plums):
            self.state.game_over = True
            return self.state

        self.state.snake.body.insert(0, next_head)
        if eats_food:
            self.state.foods.remove(next_head)
            self.state.score += POINTS_PER_APPLE
            self.state.apples_remaining = max(0, self.state.apples_remaining - 1)
            apple_number = APPLES_PER_LEVEL - self.state.apples_remaining
            self.state.growth_pending += growth_for_apple(apple_number) - 1
            if self.state.apples_remaining == 0:
                # The board is cleared: stop replacing apples and open the door.
                self.state.door_open = True
                self.state.foods.clear()
            else:
                self._replenish_foods(self.state)
        elif self.state.growth_pending > 0:
            self.state.growth_pending -= 1
        else:
            self.state.snake.body.pop()
        self._move_plums()
        return self.state

    def _advance_level(self) -> None:
        """Clear the level and rebuild the board for the next one.

        Learning note:
            The snake returns to its starting length here. That is faithful to
            the original, and it also guarantees the new maze can never close
            around a long snake that happened to be lying across the new walls.
        """

        next_level = self.state.level + 1
        score = self.state.score
        demo_mode = self.state.demo_mode

        self.state = self._new_state()
        self.state.score = score
        self.state.level = next_level
        self.state.demo_mode = demo_mode
        self.state.door_x = door_column(self._board, next_level)
        self.state.level_cleared = True
        self._apply_level_layout()
        self.state.foods.clear()
        self._replenish_foods(self.state)
        self.state.plums = self._spawn_plums(self.state, self._plums)

    def _move_plums(self) -> None:
        """Bounce every plum one cell and end the game on a head strike."""

        if not self.state.plums:
            return

        head = self.state.snake.head
        # The body deflects a plum but the head does not, which is what makes
        # the snake's own tail a usable shield. Treat the apple as solid too:
        # the original interaction is undocumented, and bouncing keeps apples
        # safe to approach instead of turning it into an invisible trap.
        blockers = (
            set(self.state.snake.body[1:])
            | self.state.obstacles
            | set(self.state.foods)
        )

        def blocked(position: Position) -> bool:
            return not self.state.board.contains(position) or position in blockers

        moved: list[Plum] = []
        for plum in self.state.plums:
            moved.append(self._bounce(plum, blocked))
        self.state.plums = moved

        if any(plum.position == head for plum in self.state.plums):
            self.state.game_over = True

    def _bounce(self, plum: Plum, blocked: Callable[[Position], bool]) -> Plum:
        """Return the plum's next cell, reflecting off whatever is in its way."""

        target = plum.advanced()
        if not blocked(target.position):
            return target

        self.state.plum_bounced = True
        sideways = Position(plum.position.x + plum.dx, plum.position.y)
        upright = Position(plum.position.x, plum.position.y + plum.dy)
        flip_x = blocked(sideways)
        flip_y = blocked(upright)
        # A clear path on both axes means the plum clipped an exact corner, so
        # it rebounds straight back the way it came.
        if not flip_x and not flip_y:
            flip_x = flip_y = True

        deflected = plum.reflected(flip_x=flip_x, flip_y=flip_y).advanced()
        if blocked(deflected.position):
            # Wedged in a pocket: hold position but keep the new heading so the
            # plum works itself free instead of vibrating on one cell forever.
            return Plum(plum.position, deflected.dx, deflected.dy)
        return deflected

    def _visible_apple_target(self, state: GameState) -> int:
        """Return how many apples should share the board at this point."""

        eaten = APPLES_PER_LEVEL - state.apples_remaining
        target = min(MAX_VISIBLE_APPLES, 1 + eaten // APPLES_PER_SPAWN_STEP)
        return min(state.apples_remaining, target)

    def _replenish_foods(self, state: GameState) -> None:
        """Spawn apples until the level's progressive visible target is met."""

        target = self._visible_apple_target(state)
        while len(state.foods) < target:
            food = self._spawn_food(state)
            if food is None:
                break
            state.foods.append(food)

    def _spawn_food(self, state: GameState) -> Position | None:
        """Choose an unoccupied cell, or return ``None`` when the board is full."""

        # Constructing valid cells first guarantees food never appears inside
        # the snake, buried in a wall, or underneath a bouncing plum.
        occupied_by_plum = {plum.position for plum in state.plums}
        available = [
            Position(x, y)
            for y in range(state.board.height)
            for x in range(state.board.width)
            if Position(x, y) not in state.snake.body
            and Position(x, y) not in state.obstacles
            and Position(x, y) not in occupied_by_plum
            and Position(x, y) not in state.foods
        ]
        if not available:
            return None
        return self._random.choice(available)
