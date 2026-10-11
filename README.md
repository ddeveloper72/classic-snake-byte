# Snakebite Reimagined

The first playable browser build of a modern Apple IIe-inspired Snakebite game:

- Python 3.15 and FastAPI backend
- Framework-independent, typed game engine
- Autonomous server game loop and authoritative WebSocket broadcasts
- Player-selectable snake speed, levels 1 to 5, for accessible play
- Selectable arrow-key, WASD, or either-scheme steering
- Zero to two bouncing perilous plums as a second difficulty dial
- Apple quota per level with an exit door that must be steered through
- Level mazes that grow from an open board to Apple IIe style walls
- Web Audio sound cues modelled on the original single-speaker beeps
- Idle demo autoplay at randomized difficulty levels
- TypeScript, Vite, and Canvas browser client
- Keyboard and touch-friendly controls
- SQLite game, player, and score persistence
- Pytest and Ruff development tooling
- Architecture and learning notes in `docs/`

## Choosing a speed

Snakebite is meant to stay playable at any reaction speed, so the pace is an
explicit setting rather than a hidden constant. Pick a level before starting a
new game:

| Level | Name | Seconds per cell |
| --- | --- | --- |
| 1 | STROLL | 0.40 |
| 2 | EASY | 0.32 |
| 3 | STEADY | 0.25 |
| 4 | BRISK | 0.19 |
| 5 | SNAKEBITE | 0.13 |

Each in-game level speeds the snake by 6 percent, but the pace never drops
below 60 percent of the chosen starting interval. A player on STROLL therefore
stays at or above 0.24 seconds per cell no matter how long the run lasts.

The selection, and the sound on/off choice, persist in `localStorage`.

## Steering

The control scheme is a stored preference, chosen in the Controls panel:

- `ARROWS` — only the arrow keys steer.
- `WASD` — only W, A, S and D steer.
- `EITHER` — both layouts work at once. This is the default.

Keys are matched case-insensitively, so Caps Lock never disables steering. The
board scrolls itself to the centre of the window when the page loads and when a
new game starts, so play always begins on a board the player can see.

## Perilous plums

The original asked "HOW MANY PLUMS?" before every game, and so does this one.
Zero to two plums travel diagonally and rebound off the board edges, the maze
walls, and the snake itself. They follow the original's asymmetry:

- A plum that reaches the snake's **head** ends the game.
- A plum that hits the snake's **body** simply bounces off, so a long tail is a
  usable shield rather than a bigger target.

Steering into a plum is just as fatal as being hit by one. Plums never spawn on
the snake, on food, inside a wall, or in the spawn corridor, and a plum that a
level change walls in is released onto open ground.

## Apples, the exit door, and level mazes

Each level holds a quota of apples (`APPLES_PER_LEVEL`). Eating the last one
does **not** advance the level. Instead it stops the apples, opens a door in the
top wall, and the player must steer the snake out through that gap. The door
column moves from level to level, and leaving the board anywhere else is still
fatal.

Level 1 is a clean board. From level 2 onwards the engine adds walls that
rebuild the "E" shape of the original game. Every wall carries a doorway, which
is deliberate coaching: threading a gap to reach an apple teaches the same skill
the exit door later demands. Three rules keep the mazes fair, and all are
covered by tests:

- A corridor in front of the spawning snake is always left open.
- Every open cell stays reachable, so food can never appear in a sealed pocket.
- Every wall has at least one doorway, so no layout is a sealed barrier.

Walls are fatal on contact, food never spawns inside one, and a wall added by a
level change can never materialise on top of the snake. Clearing a level returns
the snake to its starting length, which also guarantees the next maze can never
close around it.

## Run locally

Create the Python virtual environment and install the backend:

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m uvicorn backend.app.main:app --reload
```

The backend uses local SQLite by default at `data/snakebite.db`. To customize
it, copy `.env.example` to `.env` and edit the values. `.env` and local
database files are ignored by Git; only `.env.example` belongs in the
repository. SQLite does not require a database password.

In a second terminal, install and run the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` to play. The Vite development server proxies game
HTTP and WebSocket traffic to FastAPI, so the browser does not need a separate
CORS configuration.

Open `http://127.0.0.1:8000/docs` for generated API documentation.

Run checks:

```powershell
python -m pytest
python -m ruff check .
cd frontend
npm run build
```

Hosted database support is the next planned infrastructure slice. See
[`docs/architecture/overview.md`](docs/architecture/overview.md).
Project Goal

Recreate the classic Apple IIe game "Snakebite" using modern software engineering practices while preserving the original gameplay experience.

The project serves two purposes:

Deliver a fully playable game.
Serve as an educational reference for learning modern Python 3.15 architecture, FastAPI, testing, and AI-assisted development.
Core Vision

The game should feel like:

Apple IIe Snakebite
Fast
Responsive
Retro-inspired

but be implemented using:

Python 3.15
FastAPI
Modern web technologies
Clean Architecture principles
Test Driven Development (when practical)
Learning Requirement

Every significant implementation should include:

Learning Note

Explain:

Why this approach was chosen
Alternative approaches
Modern best practice
Historical context if relevant

Example:

Python
# Learning Note
# We use Pydantic models here instead of plain dictionaries.
# Benefits:
# - Type safety
# - Validation
# - Better IDE support
# - OpenAPI generation
Development Phases
Phase 1 - Research

Study:

Original Apple IIe Snakebite
Gameplay mechanics
Scoring
Controls
Difficulty progression

Deliverables:

Plain Text
/docs/research

containing:

gameplay.md
rules.md
scoring.md
Phase 2 - Architecture

Create:

Plain Text
/docs/architecture

Produce:

System Overview
Mermaid diagram
Domain Model

Define:

Plain Text
Snake
Food
GameBoard
Direction
GameState
Score
Player
Phase 3 - Backend Development

Build:

Plain Text
/backend

using:

Python
Python 3.15
FastAPI
Pydantic
PyTest
Required Structure
Plain Text
backend/
 
app/
├── api/
├── domain/
├── services/
├── models/
├── repositories/
├── tests/
└── main.py
Domain Driven Design

Implement:

Python
Snake
GameBoard
CollisionDetector
FoodGenerator
ScoreCalculator

Business logic must not be placed inside API endpoints.

Endpoints should be thin.

Game Engine

Create:

Python
GameEngine

Responsibilities:

move snake
detect collisions
spawn food
update score
manage speed increase
detect game over

Engine must be testable independently.

API Requirements

Implement:

Start Game
HTTP
POST /game/start
Get State
HTTP
GET /game/state
Move Snake
HTTP
POST /game/input
Pause
HTTP
POST /game/pause
``
Resume
HTTP
POST /game/resume
WebSocket Support

Implement:

Plain Text
/ws/game

Requirements:

real-time updates
low latency
server authoritative state
Frontend

Create:

Plain Text
/frontend

using:

Plain Text
TypeScript
Vite
Canvas API

Avoid game frameworks initially.

Implement rendering manually.

Educational purpose: understand the game loop.

Graphics Style

Theme:

Plain Text
Apple IIe Inspired
Modern Crisp Rendering
Retro Colour Palette

Assets:

Plain Text
Snake Head
Snake Body
Food
Background Grid
Game Over Screen

Generate placeholder assets first.

Persistence

Use:

Plain Text
SQLite
``

Tables:

Plain Text
players
scores
games
Testing

Target:

Plain Text
90% coverage

Test:

Unit Tests
Plain Text
Game Engine
Movement Logic
Collision Detection
Scoring
Integration Tests
Plain Text
API
WebSockets
Database
``
CI/CD

Create:

Plain Text
.github/workflows

Pipeline:

Lint
Type Check
Unit Test
Integration Test
Build Docker Image
Quality Standards

Require:

Plain Text
Ruff
MyPy
PyTest
Pre-Commit

All code must pass CI.

Agent Rules

When generating code:

Explain reasoning first.
Generate tests before implementation where practical.
Include learning notes.
Prefer readability over cleverness.
Follow SOLID principles.
Avoid premature optimisation.
Document architectural decisions.
Architecture Decision Records

Create:

Plain Text
/docs/adr

Examples:

Plain Text
ADR-001-use-fastapi.md
ADR-002-use-websockets.md
ADR-003-use-ddd.md
ADR-004-use-typescript.md

Each ADR must contain:

Context
Decision
Alternatives
Consequences
Educational Mode

Whenever a file is created:

Include a section:

Markdown
## What You Learned

explaining:

New concepts
Design patterns used
Python features introduced
Recommended further reading
Links to official documentation

---

# Suggested Copilot Agent Resources

I would add these files alongside the specification:

```text
.github/
├── copilot-instructions.md
├── prompts/
│   ├── architect.md
│   ├── backend-agent.md
│   ├── frontend-agent.md
│   ├── testing-agent.md
│   └── learning-agent.md

copilot-instructions.md
Markdown
# Project Rules
 
Act as a senior software architect.
 
Priorities:
 
1. Maintainability
2. Testability
3. Learning value
4. Modern Python practices
 
Always explain decisions.
 
Never introduce dependencies without justification.
 
Whenever code is generated:
- explain why
- explain trade-offs
- explain alternatives
Learning Roadmap

As you work through the project, I would expect you to learn:

Week 1
FastAPI fundamentals
Dependency Injection
Pydantic
Async programming
Week 2
Game loops
Canvas rendering
WebSockets
State management
Week 3
Docker
CI/CD
Testing
Week 4
Architecture
Domain Driven Design
Production deployment
One enhancement I would strongly consider

Rather than reproducing only the original Apple IIe version, build the architecture so that Snakebite Classic and Snakebite Enhanced are game modes:

Plain Text
Classic Mode
├── Apple IIe rules
├── Original speed
├── Original scoring
 
Enhanced Mode
├── Power-ups
├── Multiple food types
├── Obstacles
├── Leaderboards
├── Achievements