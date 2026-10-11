"""In-memory browser-session ownership for independent game instances."""

import asyncio
import secrets
import time
from dataclasses import dataclass, field

from backend.app.repositories.database import Database
from backend.app.services.game_loop import GameLoopService
from backend.app.services.persistence import PersistenceService

SESSION_COOKIE_NAME = "snakebite_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
MAX_SESSIONS = 500
SESSION_CLEANUP_INTERVAL_SECONDS = 60


@dataclass(slots=True)
class GameSession:
    """Game and persistence state owned by one opaque browser credential."""

    token: str
    game_service: GameLoopService
    persistence: PersistenceService
    last_access: float
    connections: int = 0
    action_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionCapacityError(RuntimeError):
    """Raised when the server has reached its configured session limit."""


class GameSessionManager:
    """Create, own, expire, and isolate independent player game sessions."""

    def __init__(
        self,
        database: Database,
        player_name: str,
        *,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        max_sessions: int = MAX_SESSIONS,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        if max_sessions <= 0:
            raise ValueError("max_sessions must be greater than zero")

        self._database = database
        self._player_name = player_name
        self._leaderboard_persistence = PersistenceService(
            database,
            player_name,
            initialize_database=False,
        )
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the periodic cleanup task once per application lifecycle."""

        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(),
                name="snakebite-session-cleanup",
            )

    async def stop(self) -> None:
        """Stop cleanup and release every game loop at application shutdown."""

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        async with self._lock:
            for session in tuple(self._sessions.values()):
                await self._retire_locked(session)
            self._sessions.clear()

    async def get_or_create(
        self,
        presented_token: str | None,
    ) -> GameSession:
        """Resolve the HttpOnly cookie or issue a fresh, unexposed credential."""

        async with self._lock:
            now = time.monotonic()
            await self._expire_locked(now)
            session = self._sessions.get(presented_token or "")
            if session is not None:
                session.last_access = now
                return session

            if len(self._sessions) >= self._max_sessions:
                raise SessionCapacityError("The server has reached its session limit")

            token = secrets.token_urlsafe(32)
            persistence = PersistenceService(
                self._database,
                self._player_name,
                initialize_database=False,
            )
            await persistence.initialize()
            game_service = GameLoopService(on_game_over=persistence.complete_game)
            await game_service.start_loop()
            session = GameSession(
                token=token,
                game_service=game_service,
                persistence=persistence,
                last_access=now,
            )
            self._sessions[token] = session
            return session

    async def connect(self, presented_token: str | None) -> GameSession | None:
        """Authorize a WebSocket only for an existing, unexpired cookie."""

        if presented_token is None:
            return None
        async with self._lock:
            now = time.monotonic()
            await self._expire_locked(now)
            session = self._sessions.get(presented_token)
            if session is None:
                return None
            session.connections += 1
            session.last_access = now
            return session

    async def disconnect(self, session: GameSession) -> None:
        """Release one live WebSocket reference to its owning session."""

        async with self._lock:
            session.connections = max(0, session.connections - 1)
            session.last_access = time.monotonic()

    def touch(self, session: GameSession) -> None:
        """Refresh an authorized session after activity on its WebSocket."""

        session.last_access = time.monotonic()

    async def leaderboard(self) -> list[dict[str, object]]:
        """Return completed level-ten wins from the shared public leaderboard."""

        rows = await self._leaderboard_persistence.leaderboard()
        return [dict(row) for row in rows]

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)
            async with self._lock:
                await self._expire_locked(time.monotonic())

    async def _expire_locked(self, now: float) -> None:
        expired = [
            session
            for session in self._sessions.values()
            if session.connections == 0
            and now - session.last_access >= self._ttl_seconds
        ]
        for session in expired:
            await self._retire_locked(session)
            self._sessions.pop(session.token, None)

    async def _retire_locked(self, session: GameSession) -> None:
        await session.game_service.stop_loop()
        await session.persistence.abandon_game()
