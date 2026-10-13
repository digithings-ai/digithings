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

## CLI

`src/cli.ts` drives the same configs service the TUI and the web `/devkit` route
use, so a change from the command line shows up live in both. It reads and writes
deployment-relative keys: `chrome.mode` is the same key here, in the TUI, and in
the devkit panes.

```bash
bun src/cli.ts looks                                  # every look, and which are read-only
bun src/cli.ts get datatap-trial-foundry              # the whole deployment as YAML
bun src/cli.ts get datatap-trial-foundry chrome.mode  # one key (— when unset)
bun src/cli.ts set datatap-trial-foundry chrome.theme light
bun src/cli.ts mode datatap-trial-foundry popup        # fullscreen | popup | embedded | sidebar
bun src/cli.ts export datatap-trial-foundry > look.yaml
bun src/cli.ts import datatap-trial-foundry look.yaml
bun src/cli.ts validate look.yaml
```

`mode` maps the spoken names onto the `chrome.mode` enum (`fullscreen` → `app`,
`popup` → `modal`, `embedded` → `embed`, `sidebar` → `sidebar`). `<look>` matches
an id, a path, a file name, or a label. `--url` overrides `DIGICHAT_DEVKIT_URL`
(default `http://127.0.0.1:3006`), `--json` prints machine output, and `--string`
keeps a `set` value as a string.

A `set` edits the YAML surgically: it replaces the one value line and keeps every
comment, blank line and key order, then posts the text to
`POST /api/devkit/save`, which validates the schema before it writes (and keeps a
`.bak`). A plain look wraps the deployment under `deployment:`; a host-scoped look
(e.g. `…#hosts/digithings.ai`) nests it under `hosts: <host>:`, and the CLI maps
the key there. `import` takes raw YAML for a look, or `new:<slug>.yaml` to create
one. Environment tenants are read-only and a write to one is refused.

This app is bun-managed and lives outside the root npm workspaces. It does not
extend the web route.
