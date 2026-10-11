# ADR-003: Run the game loop on the server

## Context

The first playable client requested ticks from a browser timer. That kept game
rules authoritative but allowed multiple clients to increase game speed and
made background-tab timer throttling affect gameplay.

## Decision

Run one async `GameLoopService` task for the FastAPI application lifecycle. The
service serializes input and ticks with a lock, advances the synchronous domain
engine at a fixed interval, and signals subscribed WebSocket adapters whenever
state changes.

Subscriber queues contain at most one signal. They tell adapters to serialize
the latest state instead of retaining mutable state snapshots.

## Alternatives

- Browser-owned ticks: simple, but client timing and client count affect play.
- A tick task per WebSocket: isolates connections but advances shared state more
  than once and wastes resources.
- A dedicated worker process: supports larger deployments, but adds messaging
  and operational complexity before the project needs horizontal scaling.

## Consequences

Game speed no longer depends on clients, and observers receive the same
authoritative timeline. The service is currently one in-memory game, so
multi-game sessions and process-safe coordination remain future work. The
service lifecycle and timing behavior require async integration tests.
