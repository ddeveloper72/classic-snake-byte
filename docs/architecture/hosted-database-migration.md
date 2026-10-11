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

## Demo mode and idle simulation plan

The game should support a “demo” or idle loop when no player is actively interacting with the board.

1. Add a `demo_mode` flag to the server state or game service.
2. When no player input arrives for a configurable timeout, start a simulated controller that steers the snake toward food with simple heuristics.
3. Randomize the initial level and target difficulty so the board appears more challenging over time.
4. Allow the demo to stop when a player begins a real game and resume when the session becomes idle again.

The most maintainable first version is a lightweight autopilot that chooses the next safe direction toward food, with occasional randomized turns to avoid repetitive loops. This keeps the logic in the server/service layer rather than the browser client.

## Recommended next implementation order

1. Finish the difficulty progression model in the server and frontend.
2. Add the player identity and score UI display.
3. Implement demo-mode state transitions and idle detection.
4. Prepare the hosted database adapter and environment configuration for production.
