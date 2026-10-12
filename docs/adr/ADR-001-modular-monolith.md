# ADR-001: Start with a modular monolith

## Context

Snake Byte is both a playable game and a learning project. The first milestone
needs fast feedback and a small operational footprint.

## Decision

Use one FastAPI application with explicit domain, API, model, and repository
boundaries. Keep the game engine independent from the web framework.

## Alternatives

- Separate services: rejected initially because deployment and networking would
  distract from gameplay.
- Framework-only game logic: rejected because it makes rules difficult to test.

## Consequences

The first release is simple to run locally and easy to test. The repository
boundary leaves room for SQLite persistence without coupling the domain to SQL.
