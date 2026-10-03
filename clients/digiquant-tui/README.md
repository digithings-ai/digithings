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

The header matches the public web desk. The pixel DIGIQUANT mark is on the left, then the desk control (`desk: Baseline ▾`), then the path. `/` focuses the path and filters the public web rail: the same pages, in the same order, with the same labels. Enter opens the highlighted page. `d` opens the desk list. Invite-only desks are not listed. The sidebar is that rail. `↑` `↓` moves through it when the desk list is closed. `→` or tab enters a block. Arrows move it, shift+arrows resize it.

This app is bun-managed and lives outside the root npm workspaces.

A digichat terminal tab is parked and not built here.

Terminal, Charts, and digichat stay on the rail. They are not drawn in this terminal.
