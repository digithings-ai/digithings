# digichat-devkit

OpenTUI workbench for the digichat dev kit. Bun 1.3+ reconciles terminal cells
(`box`, `text`). A side panel holds the same groups as the dev-only `/devkit`
route: deployments, Basics (Identity, Features, Models), Appearance, and
Advanced (Backend, Tools, MCP servers, Gate), plus export and validation.

The main region is that draft running. Title, welcome, placeholder, model,
tools, and MCP servers come from the selected deployment, and an edit updates
them immediately. `enter` posts the composer to `POST /api/baseline-chat` with
the draft model, tools, and MCP servers, then shows the streamed reply or the
error. `space` toggles a flag, a tool, or an MCP server.

`GET /api/devkit/configs` is the configs read (`DIGICHAT_DEVKIT_URL`, default
`http://127.0.0.1:3000`). A refused or unreachable service stays an empty
state. No sessions and no sample deployments are invented. Secrets from the
payload are not printed.

```bash
bun install
bun test
DIGICHAT_DEVKIT_URL=http://127.0.0.1:3000 bun src/index.tsx
```

`tab` moves between the composer, the settings, and the tooling strip. `↑` `↓`
moves. `enter` sends. `esc` leaves the composer. `q` quits.

This app is bun-managed and lives outside the root npm workspaces. It does not
extend the web route.
