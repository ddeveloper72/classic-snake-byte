# ADR-004: Start persistence with SQLite

## Context

Snakebite needs durable players, games, and scores, but the current project is
a single-user local development application. Introducing a hosted database now
would add credentials and infrastructure before the data model is stable.

## Decision

Use SQLite through an async repository boundary. Create `players`, `games`, and
`scores` tables at application startup. Load `DATABASE_URL` from environment
configuration, defaulting to an ignored local `data/snakebite.db` file.

Commit `.env.example` with safe defaults, but never commit `.env`, database
files, or credentials.

## Alternatives

- PostgreSQL now: stronger multi-user and deployment characteristics, but
  unnecessary operational complexity for this phase.
- Raw SQL in API routes: faster initially, but couples transport to storage and
  makes testing harder.
- Browser local storage: not authoritative and cannot support shared
  leaderboards.

## Consequences

Games and completed scores survive application restarts, and the repository can
be tested with an in-memory database. SQLite is not the final multi-instance
database; hosted deployment will require a managed database, migrations, and
secret storage such as Azure Key Vault or GitHub Actions secrets.
