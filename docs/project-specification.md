# Project Specification: Snakebite Reimagined

## Project Goal

Recreate the classic Apple IIe game "Snakebite" using modern software engineering practices while preserving the original gameplay experience.

The project serves two purposes:

1. Deliver a fully playable game.
2. Serve as an educational reference for learning modern Python 3.15 architecture, FastAPI, testing, and AI-assisted development.

---

# Core Vision

The game should feel like:

- Apple IIe Snakebite
- Fast
- Responsive
- Retro-inspired

but be implemented using:

- Python 3.15
- FastAPI
- Modern web technologies
- Clean Architecture principles
- Test Driven Development (when practical)

---

# Learning Requirement

Every significant implementation should include learning notes explaining why an approach was chosen, alternatives, modern best practice, and historical context.

---

# Development Phases

## Phase 1 - Research

Study:

- Original Apple IIe Snakebite
- Gameplay mechanics
- Scoring
- Controls
- Difficulty progression

Deliverables:

/docs/research

Containing:

- gameplay.md
- rules.md
- scoring.md

## Phase 2 - Architecture

Create:

/docs/architecture

Define:

- Snake
- Food
- GameBoard
- Direction
- GameState
- Score
- Player

## Phase 3 - Backend Development

Python 3.15, FastAPI, Pydantic and PyTest.

Recommended structure:

backend/
├── app/
│   ├── api/
│   ├── domain/
│   ├── services/
│   ├── models/
│   ├── repositories/
│   ├── tests/
│   └── main.py

---

# Domain Driven Design

Implement:

- Snake
- GameBoard
- CollisionDetector
- FoodGenerator
- ScoreCalculator

Business logic must remain outside API endpoints.

---

# Game Engine

Create a GameEngine responsible for:

- Snake movement
- Collision detection
- Food spawning
- Score updates
- Speed progression
- Game over detection

The engine must be independently testable.

---

# API Requirements

- POST /game/start
- GET /game/state
- POST /game/input
- POST /game/pause
- POST /game/resume

---

# WebSocket Support

Endpoint:

/ws/game

Requirements:

- Real-time updates
- Low latency
- Server authoritative state

---

# Frontend

Use:

- TypeScript
- Vite
- Canvas API

Avoid game frameworks initially.

---

# Persistence

Use SQLite.

Tables:

- players
- scores
- games

---

# Testing

Target 90% coverage.

Unit tests:

- Game engine
- Movement logic
- Collision detection
- Scoring

Integration tests:

- API
- WebSockets
- Database

---

# CI/CD

Pipeline:

1. Lint
2. Type Check
3. Unit Test
4. Integration Test
5. Docker Build

---

# Quality Standards

- Ruff
- MyPy
- PyTest
- Pre-Commit

---

# Agent Rules

1. Explain reasoning first.
2. Generate tests before implementation where practical.
3. Include learning notes.
4. Prefer readability.
5. Follow SOLID principles.
6. Avoid premature optimisation.
7. Document architectural decisions.

---

# Architecture Decision Records

/docs/adr

Examples:

- ADR-001-use-fastapi.md
- ADR-002-use-websockets.md
- ADR-003-use-ddd.md
- ADR-004-use-typescript.md

Each ADR must include:

- Context
- Decision
- Alternatives
- Consequences

---

# GitHub Copilot Resources

.github/
├── copilot-instructions.md
├── prompts/
│   ├── architect.md
│   ├── backend-agent.md
│   ├── frontend-agent.md
│   ├── testing-agent.md
│   └── learning-agent.md

---

# Learning Roadmap

Week 1
- FastAPI fundamentals
- Dependency Injection
- Pydantic
- Async programming

Week 2
- Game loops
- Canvas rendering
- WebSockets
- State management

Week 3
- Docker
- CI/CD
- Testing

Week 4
- Architecture
- Domain Driven Design
- Production deployment

---

# Enhancement Strategy

Build two game modes:

## Classic Mode

- Apple IIe rules
- Original speed
- Original scoring

## Enhanced Mode

- Power-ups
- Multiple food types
- Obstacles
- Leaderboards
- Achievements
