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

The top right is the same pixel DIGIQUANT mark as the web hero. The sidebar is the web desk rail (`~/pages`, slash paths, the same order and labels). `d` switches Baseline and FX Hub. `↑` `↓` moves through that rail. `→` or tab enters a block. Arrows move it, shift+arrows resize it. `/` jumps to a path.

This app is bun-managed and lives outside the root npm workspaces.

A digichat terminal tab is parked and not built here.

Terminal, Charts, and digichat stay on the rail. They are not drawn in this terminal.
