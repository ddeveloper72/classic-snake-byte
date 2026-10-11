"""Executable examples of the core Snakebite movement rules.

Fixed random seeds keep food placement deterministic so failures describe game
logic changes rather than random test data.
"""

import asyncio
from random import Random

from backend.app.domain.game import (
    APPLES_PER_LEVEL,
    MAX_DIFFICULTY,
    MAX_PLUMS,
    MIN_DIFFICULTY,
    SECONDS_PER_CELL,
    Direction,
    GameBoard,
    GameEngine,
    Plum,
    Position,
    build_obstacles,
    door_column,
    spawn_corridor,
)
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


def test_level_does_not_rise_from_score_alone() -> None:
    """Eating must never skip the exit door the player has to steer through."""

    engine = GameEngine(seed=1, difficulty=3)
    engine.state.score = 80

    assert engine.level == 1

    engine.state.level = 3

    assert engine.level == 3
    assert engine.tick_interval < SECONDS_PER_CELL[3]


def test_lowest_difficulty_is_slower_than_highest() -> None:
    gentle = GameEngine(seed=1, difficulty=MIN_DIFFICULTY)
    original = GameEngine(seed=1, difficulty=MAX_DIFFICULTY)

    assert gentle.tick_interval > original.tick_interval
    assert gentle.state.difficulty == MIN_DIFFICULTY


def test_difficulty_is_clamped_to_supported_range() -> None:
    engine = GameEngine(seed=1, difficulty=99)

    assert engine.difficulty == MAX_DIFFICULTY

    engine.set_difficulty(-5)

    assert engine.difficulty == MIN_DIFFICULTY
    assert engine.state.difficulty == MIN_DIFFICULTY


def test_gentle_difficulty_never_outruns_its_floor() -> None:
    engine = GameEngine(seed=1, difficulty=MIN_DIFFICULTY)
    engine.state.level = 100

    floor = SECONDS_PER_CELL[MIN_DIFFICULTY] * 0.6

    assert engine.tick_interval == floor


def test_first_level_has_no_obstacles() -> None:
    engine = GameEngine(seed=1)

    assert engine.state.obstacles == frozenset()


def test_later_levels_add_more_obstacles() -> None:
    board = GameBoard()

    counts = [len(build_obstacles(board, level)) for level in range(1, 6)]

    assert counts[0] == 0
    assert counts == sorted(counts)
    assert counts[4] > counts[1]


def test_obstacles_never_block_the_starting_snake() -> None:
    board = GameBoard()

    for level in range(1, 9):
        engine = GameEngine(seed=level)
        engine.state.score = (level - 1) * 40
        engine.state.level = level
        engine._apply_level_layout()

        occupied = set(engine.state.snake.body)
        assert engine.state.obstacles.isdisjoint(occupied)
        assert engine.state.food not in engine.state.obstacles
        assert build_obstacles(board, level).isdisjoint(occupied)


def test_hitting_an_obstacle_ends_the_game() -> None:
    engine = GameEngine(seed=1)
    head = engine.state.snake.head
    wall = Position(head.x + 1, head.y)
    engine.state.obstacles = frozenset({wall})

    engine.tick()

    assert engine.state.game_over is True


def test_food_never_spawns_inside_a_wall() -> None:
    engine = GameEngine(seed=7)
    engine.state.level = 5
    engine._apply_level_layout()

    for _ in range(80):
        food = engine._spawn_food(engine.state)
        assert food not in engine.state.obstacles


def test_every_open_cell_stays_reachable_on_all_levels() -> None:
    """No layout may seal a pocket, or food could spawn somewhere unreachable."""

    board = GameBoard()

    for level in range(1, 9):
        obstacles = build_obstacles(board, level)
        open_cells = {
            Position(x, y)
            for y in range(board.height)
            for x in range(board.width)
            if Position(x, y) not in obstacles
        }

        start = Position(board.width // 2, board.height // 2)
        reached = {start}
        queue = [start]
        while queue:
            current = queue.pop()
            for direction in Direction:
                dx, dy = direction.delta
                neighbour = Position(current.x + dx, current.y + dy)
                if neighbour in open_cells and neighbour not in reached:
                    reached.add(neighbour)
                    queue.append(neighbour)

        assert reached == open_cells, f"level {level} seals off part of the board"


def test_demo_level_sets_autoplay_state() -> None:
    engine = GameEngine(seed=1)

    state = engine.set_demo_level(4)

    assert state.demo_mode is True
    assert state.level == 4
    assert state.score == 120


def test_plum_count_is_clamped_to_the_original_range() -> None:
    assert GameEngine(seed=1, plums=7).plums == MAX_PLUMS
    assert GameEngine(seed=1, plums=-3).plums == 0
    assert len(GameEngine(seed=1, plums=2).state.plums) == 2
    assert GameEngine(seed=1).state.plums == []


def test_plums_never_start_in_the_snakes_lane() -> None:
    board = GameBoard()
    corridor = spawn_corridor(board)

    for seed in range(40):
        state = GameEngine(board=board, seed=seed, plums=MAX_PLUMS).state
        for plum in state.plums:
            assert plum.position not in corridor
            assert plum.position not in state.obstacles
            assert plum.position not in state.snake.body
            assert plum.position != state.food


def test_plum_travels_diagonally_across_open_ground() -> None:
    engine = GameEngine(seed=1)
    engine.state.plums = [Plum(Position(5, 5), 1, 1)]

    engine.tick()

    assert engine.state.plums[0].position == Position(6, 6)
    assert engine.state.plum_bounced is False


def test_plum_rebounds_off_the_board_edge() -> None:
    engine = GameEngine(board=GameBoard(width=8, height=8), seed=1)
    # Travelling down-right from the bottom row, so only the vertical axis
    # is obstructed and the horizontal heading must survive the bounce.
    engine.state.plums = [Plum(Position(3, 7), 1, 1)]

    engine.tick()

    plum = engine.state.plums[0]
    assert plum.position == Position(4, 6)
    assert (plum.dx, plum.dy) == (1, -1)
    assert engine.state.plum_bounced is True


def test_plum_rebounds_off_an_apple_without_moving_it() -> None:
    engine = GameEngine(seed=1)
    apple = Position(6, 6)
    engine.state.food = apple
    engine.state.plums = [Plum(Position(5, 5), 1, 1)]

    engine._move_plums()

    plum = engine.state.plums[0]
    assert plum.position == Position(4, 4)
    assert (plum.dx, plum.dy) == (-1, -1)
    assert plum.position != apple
    assert engine.state.food == apple
    assert engine.state.plum_bounced is True


def test_plum_deflects_off_the_snake_body_without_killing() -> None:
    engine = GameEngine(seed=1)
    head = engine.state.snake.head
    body_cell = engine.state.snake.body[1]
    # Aimed at the second body segment, which shields rather than kills.
    engine.state.plums = [Plum(Position(body_cell.x - 1, body_cell.y - 1), 1, 1)]

    engine.tick()

    assert engine.state.game_over is False
    assert engine.state.plum_bounced is True
    assert engine.state.snake.head != head


def test_plum_striking_the_head_ends_the_game() -> None:
    engine = GameEngine(seed=1)
    head = engine.state.snake.head
    # The snake moves right one cell this tick, so this plum arrives exactly
    # on the cell the head is about to occupy.
    engine.state.plums = [Plum(Position(head.x + 2, head.y + 1), -1, -1)]

    engine.tick()

    assert engine.state.plums[0].position == engine.state.snake.head
    assert engine.state.game_over is True


def test_steering_into_a_plum_ends_the_game() -> None:
    engine = GameEngine(seed=1)
    head = engine.state.snake.head
    engine.state.plums = [Plum(Position(head.x + 1, head.y), 1, 1)]

    engine.tick()

    assert engine.state.game_over is True


def test_plum_never_leaves_the_board_over_a_long_run() -> None:
    board = GameBoard()
    engine = GameEngine(board=board, seed=3, plums=MAX_PLUMS)
    # Walls on every side make this the harshest rebound case available.
    engine.state.level = 5
    engine._apply_level_layout()

    for _ in range(300):
        engine._move_plums()
        for plum in engine.state.plums:
            assert board.contains(plum.position)
            assert plum.position not in engine.state.obstacles


def test_level_change_releases_a_plum_trapped_in_new_walls() -> None:
    engine = GameEngine(seed=1, plums=1)
    walls = build_obstacles(engine.state.board, 5)
    engine.state.plums = [Plum(next(iter(walls)), 1, 1)]
    engine.state.level = 5

    engine._apply_level_layout()

    assert len(engine.state.plums) == 1
    assert engine.state.plums[0].position not in engine.state.obstacles


def test_food_never_spawns_under_a_plum() -> None:
    engine = GameEngine(board=GameBoard(width=6, height=6), seed=2, plums=MAX_PLUMS)

    for _ in range(50):
        food = engine._spawn_food(engine.state)
        assert all(food != plum.position for plum in engine.state.plums)


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


def _eat_until_door_opens(engine: GameEngine) -> None:
    """Teleport food onto the head's next cell until the apple quota clears."""

    while engine.state.apples_remaining > 0:
        engine.state.food = engine.state.snake.next_head()
        engine.tick()


def test_door_stays_shut_until_the_apple_quota_is_cleared() -> None:
    engine = GameEngine(seed=7)

    assert engine.state.apples_remaining == APPLES_PER_LEVEL
    assert engine.state.door_open is False

    engine.state.food = engine.state.snake.next_head()
    engine.tick()

    assert engine.state.apples_remaining == APPLES_PER_LEVEL - 1
    assert engine.state.door_open is False
    assert engine.state.food is not None


def test_clearing_the_quota_opens_the_door_and_stops_the_apples() -> None:
    engine = GameEngine(seed=7)

    _eat_until_door_opens(engine)

    assert engine.state.door_open is True
    assert engine.state.food is None
    assert engine.state.level == 1


def test_leaving_through_the_open_door_advances_the_level() -> None:
    engine = GameEngine(seed=7)
    _eat_until_door_opens(engine)

    score_before = engine.state.score
    engine.state.snake.body = [Position(engine.state.door_x, 0)]
    engine.state.snake.direction = Direction.UP
    engine.tick()

    assert engine.state.game_over is False
    assert engine.state.level == 2
    assert engine.state.level_cleared is True
    assert engine.state.score == score_before
    assert engine.state.door_open is False
    assert engine.state.apples_remaining == APPLES_PER_LEVEL
    assert engine.state.food is not None


def test_the_top_wall_still_kills_away_from_the_door() -> None:
    engine = GameEngine(seed=7)
    _eat_until_door_opens(engine)

    off_door_x = (engine.state.door_x + 3) % engine.state.board.width
    engine.state.snake.body = [Position(off_door_x, 0)]
    engine.state.snake.direction = Direction.UP
    engine.tick()

    assert engine.state.game_over is True
    assert engine.state.level == 1


def test_a_shut_door_is_not_an_exit() -> None:
    engine = GameEngine(seed=7)

    assert engine.state.door_open is False

    engine.state.snake.body = [Position(engine.state.door_x, 0)]
    engine.state.snake.direction = Direction.UP
    engine.tick()

    assert engine.state.game_over is True
    assert engine.state.level == 1


def test_the_door_moves_between_levels() -> None:
    board = GameBoard()
    columns = {door_column(board, level) for level in range(1, 9)}

    assert len(columns) > 1
    for level in range(1, 9):
        assert 0 <= door_column(board, level) < board.width


def test_the_door_is_never_buried_in_a_wall() -> None:
    board = GameBoard()
    for level in range(1, 9):
        walls = build_obstacles(board, level)
        assert Position(door_column(board, level), 0) not in walls


def test_every_maze_wall_has_a_doorway() -> None:
    """Each level's walls must be rooms to walk into, not sealed barriers."""

    board = GameBoard()
    center_y = board.height // 2
    left = 4
    right = board.width - 5
    top = center_y - 4
    bottom = center_y + 4

    for level in range(2, 9):
        walls = build_obstacles(board, level)
        top_rail = [x for x in range(left, right + 1) if Position(x, top) in walls]
        bottom_rail = [
            x for x in range(left, right + 1) if Position(x, bottom) in walls
        ]

        assert len(top_rail) < right - left + 1
        assert len(bottom_rail) < right - left + 1

        if level >= 3:
            side = [y for y in range(top, bottom + 1) if Position(left, y) in walls]
            assert len(side) < bottom - top + 1


def test_advancing_a_level_resets_the_snake_to_a_safe_length() -> None:
    engine = GameEngine(seed=11)
    engine.state.level = 4
    _eat_until_door_opens(engine)

    engine.state.snake.body = [Position(engine.state.door_x, 0)]
    engine.state.snake.direction = Direction.UP
    engine.tick()

    assert engine.state.level == 5
    assert len(engine.state.snake.body) == 3
    # The brand-new level 5 maze must not have been laid on top of the snake.
    assert not set(engine.state.snake.body) & engine.state.obstacles
