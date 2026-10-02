# digichat-devkit

OpenTUI workbench for the digichat dev kit. Bun 1.3+ reconciles terminal cells
(`box`, `text`). One screen shows the same sections as the dev-only `/devkit`
route: deployments, Basics (Identity, Features, Models), Appearance, Advanced
(Backend, Tools, MCP servers, Gate), preview, export, and validation.

`GET /api/devkit/configs` is the only read (`DIGICHAT_DEVKIT_URL`, default
`http://127.0.0.1:3000`). A refused or unreachable service stays an empty
state. No sessions and no sample deployments are invented. Secrets from the
payload are not printed.

```bash
bun install
bun test
DIGICHAT_DEVKIT_URL=http://127.0.0.1:3000 bun src/index.tsx
```

`tab` moves between panes. `↑` `↓` moves the composer caret. `q` quits.

This app is bun-managed and lives outside the root npm workspaces. It does not
extend the web route.
