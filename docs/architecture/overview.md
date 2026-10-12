# Snake Byte architecture

Snake Byte starts as a **modular monolith**: one deployable FastAPI application
with strict boundaries between the domain and adapters. This keeps the learning
project easy to run while allowing the game engine to be tested without an HTTP
server or database.

```mermaid
flowchart LR
    Input[Keyboard / touch] --> Browser[TypeScript Canvas client]
    Browser -->|POST /session| Cookie[HttpOnly session cookie]
    Browser -->|REST / WebSocket + cookie| API[FastAPI adapters]
    API --> Manager[GameSessionManager]
    Manager --> SessionA[Browser game session A]
    Manager --> SessionB[Browser game session B]
    SessionA --> LoopA[GameLoopService]
    SessionB --> LoopB[GameLoopService]
    LoopA --> EngineA[GameEngine]
    LoopB --> EngineB[GameEngine]
    EngineA --> Domain[Snake, Board, Rules]
    EngineB --> Domain
    Manager --> Persistence[SQLite repositories]
    Persistence --> Schema[(players / games / scores)]
```

## Boundaries

- `backend/app/domain`: framework-independent game rules.
- `backend/app/models`: Pydantic request and response schemas.
- `backend/app/api`: HTTP and WebSocket transport.
- `backend/app/services`: async game timing and observer coordination.
- `backend/app/repositories`: async SQLite connection and schema boundary.
- `backend/app/services/persistence.py`: game lifecycle and leaderboard writes.
- `backend/tests`: domain and adapter tests.
- `frontend/src/main.ts`: browser state synchronization, controls, and rendering.
- `frontend/vite.config.ts`: development proxy from the browser to FastAPI.

## State flow

1. The browser calls `POST /session`; FastAPI issues a random credential in an
   `HttpOnly`, `SameSite=Strict` cookie and never returns it in JSON.
2. The browser opens `/ws/game`; the cookie selects one server-owned session.
3. Keyboard or direction-pad input sends a direction intention over that socket.
4. Each session owns one `GameLoopService`, engine, and persistence lifecycle.
5. The service advances only its own engine and notifies only its own observers.
6. Canvas redraws only from the current session's authoritative snapshots.

The browser never calculates collisions, scores, growth, or food placement.
Update queues hold at most one signal, so a slow observer receives the latest
state without accumulating stale frames or affecting the game speed. REST
routes use the same cookie ownership boundary; session IDs in JSON or query
parameters are ignored.

Sessions are anonymous bearer-cookie sessions, not authenticated user
accounts. A copied complete cookie can be replayed by another client until
expiry; protecting against full-cookie theft requires account authentication.
Sessions are held in process memory and expire after 12 hours without activity.
The manager permits at most 500 concurrent sessions.
Until state moves to a shared session store, deploy one backend process/instance;
multiple workers would have different session registries and game loops.

For post-game replay, the browser records those authoritative snapshots against
active-play time. Paused time is excluded, and playback renders the recording at
2× without sending input or advancing the engine. Recording continues across
level-state replacements, so a victory replay contains levels 1 through 10.
Incoming demo snapshots are ignored during the result/replay sequence. On
completion, `POST /game/home` resets the engine to a fresh inactive state;
starting a new game cancels the sequence at any point. Only the terminal
level-10 exit sets `game_won` and earns the trophy; earlier collisions use the
same replay path but retain the `GAME OVER` presentation.

## Speed and obstacles

The tick interval is derived from a player-selected difficulty, 1 through 5,
sent once with `POST /game/start`. The engine owns the speed table, so the
browser cannot accelerate or slow the simulation by changing its own timing.
Per-level acceleration is bounded by a floor relative to the chosen base, which
keeps the gentlest setting genuinely gentle at every level.

Active player time adds a second, bounded multiplier: 5 percent every 20
seconds, capped at 25 percent. The service advances the timer by the scheduled
movement interval rather than wall-clock time, so event-loop stalls cannot
penalize the player. The domain engine ignores timer updates while paused, in
demo mode, after game over, or once the exit door is open. A new level creates
fresh state and therefore resets the timer.

The domain layer selects one of ten handcrafted obstacle patterns and publishes
it as a list of coordinates. Clearing the tenth pattern is terminal victory.
Two invariants are enforced where the layout is built, not in the renderer: the
spawn corridor stays clear, and every open cell remains reachable. A layout
applied mid-game subtracts the current snake body, so levelling up can never
kill the player instantly.

The state snapshot carries `foods` as a coordinate list because several apples
can now coexist. The engine replenishes that list from one visible apple toward
five as each group of three is eaten, up to a fixed quota of 15. Accelerating
growth is also authoritative: extra tail cells are stored as pending growth and
released over later ticks, avoiding duplicate body coordinates.

Each game loop sleeps on a separate, shorter idle interval when its game is
not running, so a slow difficulty does not delay demo-mode detection.

## Player identity and winner persistence

The browser normalizes a 24-character player name, keeps it in `localStorage`,
and sends it only when starting a game. Pydantic independently validates the
same boundary. Persistence resolves the name with bound SQLite parameters and
associates that player with the new game; the configured `PLAYER_NAME` remains
the fallback for clients that omit it.

`GameSessionManager` creates an independent `GameLoopService` and
`PersistenceService` for each browser cookie. The 256-bit random cookie is
`HttpOnly`, `SameSite=Strict`, `Secure` on non-local hosts, and is not exposed in
application JSON, to page JavaScript, in URLs, or in request bodies. DevTools
can still inspect or copy the cookie. This blocks ID-only session substitution;
it does not prevent someone from replaying a complete stolen cookie.

Completed games persist their authoritative final level and victory flag. The
public leaderboard joins scores back to games and admits only level-10 wins,
then returns the highest ten. Additive startup migration gives older databases
these columns with historical results marked as non-wins because a score alone
cannot prove victory.

## Learning note

The engine is deliberately independent of FastAPI. A game loop, a terminal
client, and a WebSocket adapter can all call the same domain operations. A
microservice split would add deployment and networking complexity without
helping the first playable version.

The application service uses an async lock to serialize player input and timed
movement. It publishes lightweight signals rather than importing WebSocket
types, preserving the boundary between coordination and transport.

SQLite is intentionally local for this phase. `DATABASE_URL` is loaded from
the environment or an ignored `.env` file, and the default local database has
no credentials. A future managed database can use the same setting without
putting secrets in source control.

Canvas is used instead of a frontend game framework because the game is a small
fixed grid with no physics, scene graph, or asset pipeline. This makes the
rendering loop visible to learners and keeps game rules in Python rather than
duplicating them in TypeScript.
