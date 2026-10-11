"""Lifecycle-managed game timing and state-change notifications.

Learning note:
    The synchronous ``GameEngine`` owns rules, while this service owns async
    coordination. Separating those responsibilities keeps domain tests fast and
    makes timing an infrastructure concern that can evolve independently.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from random import Random

from backend.app.domain.game import (
    MAX_DIFFICULTY,
    MAX_PLUMS,
    MAZE_COUNT,
    MIN_PLUMS,
    Direction,
    GameEngine,
    GameState,
    Position,
)

StateSignal = asyncio.Queue[None]


class GameLoopService:
    """Run one authoritative game and notify all connected observers."""

    def __init__(
        self,
        engine: GameEngine | None = None,
        tick_interval: float = 0.16,
        on_game_over: Callable[[GameState], Awaitable[None]] | None = None,
        *,
        idle_timeout: float = 5.0,
        random_source: Random | None = None,
    ) -> None:
        if tick_interval <= 0:
            raise ValueError("tick_interval must be greater than zero")
        if idle_timeout < 0:
            raise ValueError("idle_timeout cannot be negative")

        self._engine = engine or GameEngine()
        self._on_game_over = on_game_over
        self._started = False
        self._last_interaction = time.monotonic()
        self._idle_timeout = idle_timeout
        self._idle_poll_interval = min(tick_interval, 0.25)
        self._random = random_source or Random()
        self._lock = asyncio.Lock()
        self._subscribers: set[StateSignal] = set()
        self._task: asyncio.Task[None] | None = None

    @property
    def state(self) -> GameState:
        """Return the current state for immediate serialization."""

        return self._engine.state

    @property
    def started(self) -> bool:
        """Return whether the current state belongs to a started game."""

        return self._started

    @property
    def demo_mode(self) -> bool:
        """Return whether the current game is being played by the idle demo."""

        return self.state.demo_mode

    def set_game_over_handler(
        self,
        handler: Callable[[GameState], Awaitable[None]],
    ) -> None:
        """Register persistence or analytics work for completed games."""

        self._on_game_over = handler

    async def start_loop(self) -> None:
        """Start the background timing task once per application lifecycle."""

        if self._task is None:
            self._task = asyncio.create_task(
                self._run(),
                name="snakebite-game-loop",
            )

    async def stop_loop(self) -> None:
        """Cancel and await the background timing task."""

        if self._task is None:
            self._started = False
            self.state.demo_mode = False
            return

        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._started = False
        self.state.demo_mode = False

    async def start_game(
        self,
        difficulty: int | None = None,
        plums: int | None = None,
    ) -> GameState:
        """Reset the engine and enable autonomous movement.

        Args:
            difficulty: Optional player-selected pace from 1 to 5. Omitting it
                keeps the pace already chosen for this service.
            plums: Optional perilous plum count from 0 to 2. Omitting it keeps
                the count already chosen for this service.
        """

        async with self._lock:
            if difficulty is not None:
                self._engine.set_difficulty(difficulty)
            if plums is not None:
                self._engine.set_plums(plums)
            state = self._engine.reset()
            self._started = True
            self._record_player_interaction()
            self._notify_subscribers()
            return state

    async def start_demo_game(self) -> GameState:
        """Launch an autonomous demo run at a randomly selected difficulty."""

        async with self._lock:
            return self._start_demo_locked()

    async def turn(self, direction: Direction) -> GameState:
        """Apply a direction request to an active game."""

        async with self._lock:
            if self._started:
                self._record_player_interaction()
                self._engine.turn(direction)
                self._notify_subscribers()
            return self.state

    async def pause(self) -> GameState:
        """Pause movement while preserving the current board."""

        async with self._lock:
            if self._started:
                self._record_player_interaction()
                self._engine.pause()
                self._notify_subscribers()
            return self.state

    async def resume(self) -> GameState:
        """Resume autonomous movement for a paused active game."""

        async with self._lock:
            if self._started:
                self._record_player_interaction()
                self._engine.resume()
                self._notify_subscribers()
            return self.state

    def subscribe(self) -> StateSignal:
        """Register an observer and return its coalescing update queue."""

        signals: StateSignal = asyncio.Queue(maxsize=1)
        self._subscribers.add(signals)
        return signals

    def unsubscribe(self, signals: StateSignal) -> None:
        """Stop sending state-change signals to an observer."""

        self._subscribers.discard(signals)

    async def _run(self) -> None:
        """Advance active games while scaling the pace by difficulty and level."""

        while True:
            # An idle service polls on a short fixed timer so a slow difficulty
            # never delays the demo; a running game paces on the engine's speed.
            if self._started:
                scheduled_interval = self._engine.tick_interval
                timed_state = self.state
                was_paused = timed_state.paused
                was_demo_before_sleep = timed_state.demo_mode
                await asyncio.sleep(scheduled_interval)
            else:
                scheduled_interval = 0.0
                timed_state = None
                was_paused = False
                was_demo_before_sleep = False
                await asyncio.sleep(self._idle_poll_interval)
            async with self._lock:
                if not self._started:
                    if time.monotonic() - self._last_interaction >= self._idle_timeout:
                        self._start_demo_locked()
                    continue

                state = self.state
                if state.game_over:
                    self._started = False
                    state.demo_mode = False
                    self._last_interaction = time.monotonic()
                    self._notify_subscribers()
                    continue

                if state.paused:
                    continue

                is_demo = self.demo_mode
                if is_demo:
                    self._engine.turn(self._demo_direction())
                elif (
                    timed_state is state
                    and not was_paused
                    and not was_demo_before_sleep
                ):
                    self._engine.advance_level_time(scheduled_interval)

                self._engine.tick()
                if self.state.game_over:
                    if not is_demo and self._on_game_over is not None:
                        await self._on_game_over(self.state)
                    self._started = False
                    self.state.demo_mode = False
                    self._last_interaction = time.monotonic()
                self._notify_subscribers()

    def _start_demo_locked(self) -> GameState:
        """Start a random difficulty demo run while no human session is active."""

        target_level = self._random.randint(1, MAZE_COUNT)
        self._engine.set_difficulty(self._random.randint(2, MAX_DIFFICULTY))
        # Attract mode advertises the perilous plums too, so a passer-by sees
        # the hazard that makes the higher settings worth trying.
        self._engine.set_plums(self._random.randint(MIN_PLUMS, MAX_PLUMS))
        state = self._engine.set_demo_level(target_level)
        self._started = True
        self._last_interaction = time.monotonic()
        self._notify_subscribers()
        return state

    def _record_player_interaction(self) -> None:
        """Transfer control from demo mode and restart the idle timer."""

        self.state.demo_mode = False
        self._last_interaction = time.monotonic()

    def _demo_direction(self) -> Direction:
        """Choose the next safe turn for the autoplay routine."""

        head = self.state.snake.head
        # With the apples cleared the only worthwhile target is the exit door,
        # so attract mode demonstrates the level-clearing run too.
        if self.state.foods:
            target = min(
                self.state.foods,
                key=lambda food: abs(food.x - head.x) + abs(food.y - head.y),
            )
        else:
            target = Position(self.state.door_x, 0)

        candidates: list[Direction] = []
        for direction in Direction:
            reverses_into_body = (
                len(self.state.snake.body) > 1
                and direction == self.state.snake.direction.opposite
            )
            if reverses_into_body:
                continue
            dx, dy = direction.delta
            next_head = Position(head.x + dx, head.y + dy)
            leaves_by_door = (
                self.state.door_open
                and next_head.y < 0
                and next_head.x == self.state.door_x
            )
            if leaves_by_door:
                return direction
            if not self.state.board.contains(next_head):
                continue
            if next_head in self.state.snake.body[:-1]:
                continue
            if next_head in self.state.obstacles:
                continue
            # A demo that drove into a plum would die in seconds, which is a
            # poor advertisement for the higher settings.
            if any(plum.position == next_head for plum in self.state.plums):
                continue
            candidates.append(direction)

        if not candidates:
            return self.state.snake.direction

        scored = sorted(
            candidates,
            key=lambda direction: (
                abs((head.x + direction.delta[0]) - target.x)
                + abs((head.y + direction.delta[1]) - target.y),
                self._random.random(),
            ),
        )

        if self.state.level >= 3 and self._random.random() < 0.2:
            return self._random.choice(scored[: min(2, len(scored))])
        return scored[0]

    def _notify_subscribers(self) -> None:
        """Signal observers once, coalescing updates for slow clients."""

        for signals in self._subscribers:
            if signals.empty():
                signals.put_nowait(None)
