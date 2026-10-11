"""Executable examples of the core Snakebite movement rules.

Fixed random seeds keep food placement deterministic so failures describe game
logic changes rather than random test data.
"""

import asyncio
from random import Random

from backend.app.domain.game import Direction, GameBoard, GameEngine, Position
from backend.app.services.game_loop import GameLoopService


def test_tick_moves_snake_and_preserves_length() -> None:
    engine = GameEngine(seed=1)
    before = engine.state.snake.head

    engine.tick()

    assert engine.state.snake.head == Position(before.x + 1, before.y)
    assert len(engine.state.snake.body) == 3


def test_wall_collision_ends_game() -> None:
    engine = GameEngine(board=GameBoard(width=4, height=4), seed=1)
    engine.state.snake.body = [Position(3, 2)]

    engine.tick()

    assert engine.state.game_over is True


def test_opposite_turn_is_ignored() -> None:
    engine = GameEngine(seed=1)

    engine.turn(Direction.LEFT)

    assert engine.state.snake.direction is Direction.RIGHT


def test_eating_food_increases_score_and_length() -> None:
    engine = GameEngine(seed=1)
    head = engine.state.snake.head
    engine.state.food = Position(head.x + 1, head.y)

    engine.tick()

    assert engine.state.score == 10
    assert engine.state.level == 1
    assert len(engine.state.snake.body) == 4


def test_level_rises_as_score_increases() -> None:
    engine = GameEngine(seed=1)
    engine.state.score = 80

    assert engine.level == 3
    assert engine.tick_interval == 0.13


def test_demo_level_sets_autoplay_state() -> None:
    engine = GameEngine(seed=1)

    state = engine.set_demo_level(4)

    assert state.demo_mode is True
    assert state.level == 4
    assert state.score == 120


def test_game_loop_can_launch_demo_mode() -> None:
    async def run_test() -> None:
        service = GameLoopService()
        state = await service.start_demo_game()
        assert state.demo_mode is True
        assert 1 <= state.level <= 5

    asyncio.run(run_test())


def test_game_loop_automatically_starts_demo_after_idle_timeout() -> None:
    async def run_test() -> None:
        service = GameLoopService(
            tick_interval=0.01,
            idle_timeout=0,
            random_source=Random(0),
        )
        signals = service.subscribe()
        await service.start_loop()
        try:
            await asyncio.wait_for(signals.get(), timeout=0.5)
            assert service.started is True
            assert service.demo_mode is True
            assert service.state.demo_mode is True
            assert service.state.level == 4
            assert service.state.score == 120
        finally:
            service.unsubscribe(signals)
            await service.stop_loop()

    asyncio.run(run_test())


def test_pause_and_resume_take_over_authoritative_demo_state() -> None:
    async def run_test() -> None:
        service = GameLoopService()

        for action in (service.pause, service.resume):
            await service.start_demo_game()
            state = await action()

            assert service.demo_mode is False
            assert state.demo_mode is False

    asyncio.run(run_test())


def test_demo_game_over_clears_authoritative_demo_state() -> None:
    async def run_test() -> None:
        service = GameLoopService(tick_interval=0.01, idle_timeout=60)
        await service.start_demo_game()
        service.state.game_over = True
        signals = service.subscribe()
        await service.start_loop()
        try:
            await asyncio.wait_for(signals.get(), timeout=0.5)
            assert service.started is False
            assert service.demo_mode is False
            assert service.state.demo_mode is False
        finally:
            service.unsubscribe(signals)
            await service.stop_loop()

    asyncio.run(run_test())


def test_player_turn_takes_over_authoritative_demo_state() -> None:
    async def run_test() -> None:
        service = GameLoopService()
        await service.start_demo_game()

        state = await service.turn(Direction.DOWN)

        assert service.started is True
        assert service.demo_mode is False
        assert state.demo_mode is False
        assert state.snake.direction is Direction.DOWN

    asyncio.run(run_test())
