"""Lifecycle-managed game timing and state-change notifications.

Learning note:
    The synchronous ``GameEngine`` owns rules, while this service owns async
    coordination. Separating those responsibilities keeps domain tests fast and
    makes timing an infrastructure concern that can evolve independently.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from backend.app.domain.game import Direction, GameEngine, GameState, Position

StateSignal = asyncio.Queue[None]


class GameLoopService:
    """Run one authoritative game and notify all connected observers."""

    def __init__(
        self,
        engine: GameEngine | None = None,
        tick_interval: float = 0.16,
        on_game_over: Callable[[GameState], Awaitable[None]] | None = None,
    ) -> None:
        if tick_interval <= 0:
            raise ValueError("tick_interval must be greater than zero")

        self._engine = engine or GameEngine(base_tick_interval=tick_interval)
        self._tick_interval = tick_interval
        self._on_game_over = on_game_over
        self._started = False
        self._demo_mode = False
        self._last_interaction = time.monotonic() - tick_interval
        self._idle_timeout = 5.0
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

        return self._demo_mode

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
            return

        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._started = False

    async def start_game(self) -> GameState:
        """Reset the engine and enable autonomous movement."""

        async with self._lock:
            state = self._engine.reset()
            state.demo_mode = False
            self._started = True
            self._demo_mode = False
            self._last_interaction = time.monotonic()
            self._notify_subscribers()
            return state

    async def start_demo_game(self) -> GameState:
        """Launch an autonomous demo run at a randomly selected difficulty."""

        async with self._lock:
            target_level = random.randint(1, 5)
            state = self._engine.set_demo_level(target_level)
            self._started = True
            self._demo_mode = True
            self._last_interaction = time.monotonic()
            self._notify_subscribers()
            return state

    async def turn(self, direction: Direction) -> GameState:
        """Apply a direction request to an active game."""

        async with self._lock:
            if self._started:
                self._demo_mode = False
                self._last_interaction = time.monotonic()
                self._engine.turn(direction)
                self._notify_subscribers()
            return self.state

    async def pause(self) -> GameState:
        """Pause movement while preserving the current board."""

        async with self._lock:
            if self._started:
                self._demo_mode = False
                self._last_interaction = time.monotonic()
                self._engine.pause()
                self._notify_subscribers()
            return self.state

    async def resume(self) -> GameState:
        """Resume autonomous movement for a paused active game."""

        async with self._lock:
            if self._started:
                self._demo_mode = False
                self._last_interaction = time.monotonic()
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
        """Advance active games while scaling the pace by the level."""

        while True:
            await asyncio.sleep(self._tick_interval)
            async with self._lock:
                if not self._started and not self._demo_mode:
                    if time.monotonic() - self._last_interaction >= self._idle_timeout:
                        await self._start_demo_locked()
                    continue

                state = self.state
                if state.game_over:
                    self._started = False
                    self._demo_mode = False
                    self._notify_subscribers()
                    continue

                if state.paused:
                    continue

                if self._demo_mode:
                    self._engine.turn(self._demo_direction())

                self._engine.tick()
                if self.state.game_over and self._on_game_over is not None:
                    await self._on_game_over(self.state)
                    self._started = False
                    self._demo_mode = False
                self._notify_subscribers()

    async def _start_demo_locked(self) -> None:
        """Start a random difficulty demo run while no human session is active."""

        target_level = random.randint(1, 5)
        state = self._engine.set_demo_level(target_level)
        self._started = True
        self._demo_mode = True
        self._last_interaction = time.monotonic()
        self.state.demo_mode = True
        self._notify_subscribers()

    def _demo_direction(self) -> Direction:
        """Choose the next safe turn for the autoplay routine."""

        head = self.state.snake.head
        candidates: list[Direction] = []
        for direction in Direction:
            if len(self.state.snake.body) > 1 and direction == self.state.snake.direction.opposite:
                continue
            dx, dy = direction.delta
            next_head = Position(head.x + dx, head.y + dy)
            if not self.state.board.contains(next_head):
                continue
            if next_head in self.state.snake.body[:-1]:
                continue
            candidates.append(direction)

        if not candidates:
            return self.state.snake.direction

        scored = sorted(
            candidates,
            key=lambda direction: (
                abs((head.x + direction.delta[0]) - self.state.food.x)
                + abs((head.y + direction.delta[1]) - self.state.food.y),
                random.random(),
            ),
        )

        if self.state.level >= 3 and random.random() < 0.2:
            return random.choice(scored[: min(2, len(scored))])
        return scored[0]

    def _notify_subscribers(self) -> None:
        """Signal observers once, coalescing updates for slow clients."""

        for signals in self._subscribers:
            if signals.empty():
                signals.put_nowait(None)
