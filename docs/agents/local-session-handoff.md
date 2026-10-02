# Local session handoff

What the next Cursor session on Chris’s MacBook runs. Branch `cursor/ui-surfaces-d8c5`, draft PR 4986. Checked against this tree: Makefile, package scripts, `apps/dashboard-api/.dev.vars.example`, `apps/dashboard-api/wrangler.toml`, `apps/digiquant-web` dev scripts, `clients/digiquant-tui`, and digichat dev.

Work in `~/Code/digithings-ui-surfaces` on `cursor/ui-surfaces-d8c5`. Do not merge PR 4986. Do not push `main`. Do not force-push. If the fast-forward below does not apply, stop.

## Checkout

On this Mac, `origin` is `https://origin.cursor.com/chrizefan/digithings.git` and `github` is `https://github.com/digithings-ai/digithings.git`. Fetch the desk branch from `github`.

`~/Code/digithings` is dirty and stays on `task/4761-phase3-image-bake`. Do not check out `cursor/ui-surfaces-d8c5` there.

The desk worktree is `~/Code/digithings-ui-surfaces`. `git -C ~/Code/digithings-ui-surfaces pull` is wrong if that worktree is detached. Fast-forward it instead:

```bash
git -C ~/Code/digithings-ui-surfaces fetch github cursor/ui-surfaces-d8c5 && git -C ~/Code/digithings-ui-surfaces merge --ff-only github/cursor/ui-surfaces-d8c5
```

Run the rest of this handoff from `~/Code/digithings-ui-surfaces`. Repeat that fetch and fast-forward before launching digichat clients. Other passes may still be landing `clients/digichat-tui` and `clients/digichat-devkit`.

## Dashboard API (port 8788)

From `apps/dashboard-api` (the README in that directory):

```bash
cp .dev.vars.example .dev.vars
npx wrangler dev --port 8788
```

`.dev.vars` is gitignored (`apps/dashboard-api/.gitignore`). Paste keys only into that file. Do not commit it.

`npm run dev --workspace dashboard-api` is `wrangler dev` with no port. This check uses the README command, which binds 8788.

Worker URL: `http://127.0.0.1:8788`. Liveness is `GET /healthz` (`{"ok": true, "service": "dashboard-api"}`).

Env names the files actually use:

| Name | Where |
| --- | --- |
| `SUPABASE_URL` | `wrangler.toml` `[vars]`. Core project URL. Not a key. |
| `SUPABASE_SERVICE_ROLE_KEY` | Core service role. Empty in `.dev.vars.example`. Paste locally. Named in the `wrangler.toml` secrets comment. |
| `TWELVEX_SUPABASE_URL` | twelve-x project URL. Empty in the example. Not in `wrangler.toml`. |
| `TWELVEX_SUPABASE_SERVICE_KEY` | twelve-x key. Empty in the example. The name is `SERVICE_KEY`, not `SERVICE_ROLE_KEY`. |
| `DASHBOARD_DEV_CALLER` | Example value `enterprise+12x`. Local caller when the request has no `x-digi-tier` / `x-digi-groups`. |
| `DASHBOARD_API_ALLOWED_ORIGINS` | Example value `http://localhost:3930,http://127.0.0.1:3930` (digiquant-app). |
| `MCP_EDGE_KEY` | Local placeholder already in the example. Leave it. Do not copy a deployed secret into the repo. |

A missing core service role is not a twelve-x problem, and the reverse is not a core problem. Leave both twelve-x fields empty until you have that project. FX reads then fail closed.

## Real brief, stub, and 502

Open `GET http://127.0.0.1:8788/brief` before any UI.

`GET /brief` with no `SUPABASE_SERVICE_ROLE_KEY` is the secretless stub lane: HTTP 200, not 502. The body is a fixture. Treat it as a stub when you see any of `99.909`, `204.040`, `204.04`, or `legacy_estimate`. Those marks are the worker doubles in `apps/dashboard-api/src/stubs.ts` (NAV tip `99.909` with `legacy_estimate`, series tip `204.04`). The desk and the OpenTUI withhold that body. They show: `The official API returned a stub envelope, not a house-book read.` They do not paint those numbers.

A real brief row is HTTP 200 whose JSON does not contain those marks. It is a house-book read, not the fixture dates and NAV in the stub.

`502` with `upstream_empty` and message `core supabase is not configured` is a table read (`table-read.ts`, project `core`) that ran without both `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Brief blocks that are table reads (`/brief/decision`, `/brief/risks`, and the other domain routes) do this. `GET /brief` itself does not: without the key it stays the 200 stub.

`502` with message `twelvex supabase is not configured` is a twelve-x read missing `TWELVEX_SUPABASE_URL` or `TWELVEX_SUPABASE_SERVICE_KEY`. That is FX, not the house book.

An empty official read is a success with no values. The pane sentence is `This read returned no values.` A failed route is `{route} failed ({status}): {message}`. Neither case invents a price.

## Web desk

Port 3910 is `dev:local`, not `dev`. From the repo root:

```bash
npm run dev:local --workspace digiquant-web
```

That script is `next dev --hostname 127.0.0.1 --port 3910`. Open `http://127.0.0.1:3910`. `npm run dev --workspace digiquant-web` does not pass a port.

Leave `NEXT_PUBLIC_DASHBOARD_API_URL` and `NEXT_PUBLIC_DQ_API_URL` unset. On loopback the desk calls same-origin `/official-api`, and `apps/digiquant-web/next.config.mjs` rewrites that to `http://127.0.0.1:8788`. You do not add port 3910 to `DASHBOARD_API_ALLOWED_ORIGINS` for this path.

Trailing slash is on. `/app` and `/app/` are the brief. Also open:

- `http://127.0.0.1:3910/app/brief/`
- `http://127.0.0.1:3910/app/portfolio/`
- `http://127.0.0.1:3910/app/pipeline/`
- `http://127.0.0.1:3910/app/strategies/`
- `http://127.0.0.1:3910/app/fx/`
- `http://127.0.0.1:3910/app/tools/charts/`
- `http://127.0.0.1:3910/app/tools/terminal/`
- `http://127.0.0.1:3910/app/tools/chat/`

`/dashboard` redirects to `/app` (308, including `/dashboard/`). The old dashboard package is not the destination.

## OpenTUI

From `clients/digiquant-tui` (README in that directory; Bun 1.3+):

```bash
bun install
DQ_API_URL=http://127.0.0.1:8788 bun src/index.tsx
```

`↑` `↓` changes page. `/` jumps to a path (`/brief`, `/portfolio`, `/pipeline`, `/strategies`, `/fx`, and the nested paths in that README).

Renders correctly means the same official read as the web pane on that route: same API, same withhold rules. An empty route shows `This read returned no values.` A stub shows the stub sentence and not `99.909` or `204.04`. A 502 shows the failed-route sentence with the API message. No invented prices.

`/app/tools/terminal/`, `/app/tools/charts/`, and `/app/tools/chat/` are browser pages. This terminal does not draw them.

## Homepage hero

Leave the digiquant homepage hero (`http://127.0.0.1:3910/`, `QuantField`) as it is. Do not retune it while checking desk data. It is not a house-book read. A stub or a 502 on `/brief` is not a reason to change the hero.

## Digichat

`clients/digichat-tui` is on this branch. From that directory (its README):

```bash
bun install
DQ_API_URL=http://127.0.0.1:8788 bun src/index.tsx
```

It reads `/chat/sessions`, `/chat/sessions/current`, and `/chat/sessions/current/messages`. A 502 or 503 stays an empty screen. It does not invent a thread.

`clients/digichat-devkit` is on this branch. From that directory (its README), after the fast-forward above:

```bash
bun install
bun test
DIGICHAT_DEVKIT_URL=http://127.0.0.1:3000 bun src/index.tsx
```

The only read is `GET /api/devkit/configs` (`DIGICHAT_DEVKIT_URL`, default `http://127.0.0.1:3000`). A refused or unreachable service stays empty. It does not invent sessions or sample deployments, and it does not print secrets. If the directory is missing after the fast-forward, the cloud pass is still landing: run the fetch and fast-forward again, then follow the README. Do not invent a launch command.

Web digichat, from the repo root:

```bash
make digichat-dev
```

That is `cd apps/digichat && npm run dev` (`next dev --hostname 127.0.0.1`). The Makefile serves it at `http://127.0.0.1:3000`.

Desk chat GETs stay 502 until digichat is configured. `GET /chat/sessions` (and the current-session and messages GETs) return `502` `upstream_empty` with message `digichat is not configured`. Starting `make digichat-dev` does not clear that. The worker has no digichat database. Do not invent sessions to fill the pane.

## Visual check order

1. API `GET /brief` on port 8788. Decide stub, real row, or 502 before opening a UI.
2. Desk brief in the browser (`/app` and `/app/brief/`).
3. OpenTUI brief (`clients/digiquant-tui`, page `/brief`).
4. The other desk pages: portfolio, pipeline, strategies, FX.
5. Charts (`/app/tools/charts/`), then the terminal link (`/app/tools/terminal/`).
6. Homepage. Look only. Do not retune the hero.
7. Digichat: desk `/app/tools/chat/` (expect the 502 empty state), then `clients/digichat-tui`, then `clients/digichat-devkit` if that directory is present after the fast-forward, then `make digichat-dev`.

## Do not

- Do not apply `apps/dashboard-api/migrations-draft/`.
- Do not edit `digikey/` or `digiquant/brokers/`.
- Do not merge PR 4986 from this session.
- Do not push `main`.

## Terminal-first (2026-10-02)

Dashboards, digichat, and the dev kit are terminal bases with a web front. Marketing pages for digithings and digiquant stay websites. Self-hosters install the terminal locally.
