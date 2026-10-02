# digiquant-tui

OpenTUI spine for the digiquant desk. Bun 1.3+ reconciles terminal cells
(`box`, `text`, `input`). Each block is one read of the official dashboard
API (`http://127.0.0.1:8788`, override with `DQ_API_URL`). A missing field
is an em dash. An empty payload stays an empty state. Stub envelopes,
including the fixture ledger, are withheld.

```bash
bun install
DQ_API_URL=http://127.0.0.1:8788 bun src/index.tsx
```

`↑` `↓` changes page. `→` or tab enters a block. Arrows move it, shift+arrows resize it. `/` jumps to a path (`/brief`, `/portfolio`, `/portfolio/holdings`, `/portfolio/attribution`, `/portfolio/ledger`, `/portfolio/theses`, `/portfolio/tearsheet`, `/performance`, `/pipeline`, `/strategies`, `/strategies/detail`, `/strategies/deploy`, `/fx`, `/fx/ideas`, `/fx/watch`, `/fx/rates`, `/fx/settings`).

This app is bun-managed and lives outside the root npm workspaces.

A digichat terminal tab is parked and not built here.

Bloomberg, LuxAlgo, LuxAlgo charts, and chat are web-only and are not in
this terminal. A later pass transports this spine to the web. That transport
is not built here.
