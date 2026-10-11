# ADR-002: Render the first client with Canvas

## Context

Snakebite needs responsive grid rendering, keyboard and touch input, and a
low-latency connection to the authoritative backend. The project also aims to
teach the underlying browser APIs.

## Decision

Use TypeScript, Vite, and the Canvas 2D API without a game framework. The client
renders state received from FastAPI and sends only player intentions and
temporary tick messages.

## Alternatives

- DOM elements for every cell: simple initially, but creates unnecessary
  layout work and spreads rendering across many elements.
- A game framework: useful for physics and scenes, but excessive for a fixed
  Snakebite grid and less transparent for learners.
- Client-authoritative rules: responsive, but duplicates the Python engine and
  makes cheating or divergent states more likely.

## Consequences

The renderer stays compact and the backend remains the source of truth. Canvas
content needs explicit accessible controls and labels. Tick ownership still
needs to move from the browser to a server-side loop before supporting several
simultaneous observers.
