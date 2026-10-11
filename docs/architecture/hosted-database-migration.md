# Hosted database migration plan

## Goal

Keep the game architecture stable while shifting from local SQLite development data to a hosted database in a production or shared-environment deployment.

## Current state

The application currently reads `DATABASE_URL` from environment variables or a local `.env` file. The repository boundary is isolated behind `Database`, and the domain engine remains unaware of persistence details. This boundary is the correct seam for a production migration.

## Recommended target architecture

1. Keep the `Database` abstraction and SQL schema contract stable.
2. Swap only the concrete adapter implementation to a hosted provider such as PostgreSQL.
3. Use environment-managed secrets (`DATABASE_URL`, credentials, and service connection settings) instead of committed config.
4. Preserve the same repository methods and data model so game logic and API contracts do not change.

## Migration steps

### 1. Add a provider-agnostic configuration layer

- Validate `DATABASE_URL` in the app settings.
- Keep local SQLite as the default for development.
- Add production-safe defaults for hosted credentials via environment injection.

### 2. Introduce a hosted database adapter

- Replace the current SQLite-specific connection implementation with a provider-specific adapter that preserves the same SQL interface.
- For Azure-friendly deployments, PostgreSQL is a strong fit because it supports concurrency, managed backups, and production reliability.
- Keep migrations in code so schema changes are repeatable.

### 3. Add a schema migration tool

- Use an explicit migration flow rather than ad hoc `CREATE TABLE IF NOT EXISTS` statements once the project grows beyond local development.
- Track schema versions and ensure idempotent deployment patterns.

### 4. Protect secrets

- Keep `.env` locally ignored.
- Use Azure Key Vault, App Service environment variables, or a managed secret store in deployment.
- Do not commit production credentials or database passwords to GitHub.

## Demo mode and idle simulation

The game runs a server-authoritative demo after five seconds without an active
game. Each demo starts at a randomly selected level from 1 through 5 and uses
the same level-scaled tick interval as a player game.

The simulated controller chooses safe directions toward food and introduces
limited variation at higher levels. `demo_mode` is part of the authoritative
state, so all clients show the same mode. Starting a game or using a gameplay
control transfers control to the player and clears that state immediately.
Completed demos are not written to the player leaderboard.

The controller remains in the server service rather than the browser, which
prevents clients from simulating different games.

## Recommended next implementation order

1. Prepare the hosted database adapter and environment configuration for production.
2. Add schema migrations for hosted deployments.
3. Improve demo pathfinding if longer and more strategic runs are desired.
