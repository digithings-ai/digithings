# Self-host local dev session (DIG-2771, plan slice S3)

Run the digithings Workers locally with `wrangler dev`, against
`docker-compose.yml` services, in one session, with fixed ports and persisted
state. No production changes, no spending.

Two pieces, neither of which edits application source:

| file | role |
|---|---|
| `container_shim.ts` | runtime. A Durable Object base class that maps a container class + target port to a compose service. |
| `generate_dev_configs.py` | build time. Renders a dev config and an entry point per worker from that worker's real `wrangler.toml`. |

## Why a shim exists

`wrangler dev` cannot run Cloudflare Containers reliably. In production each
container class fronts one or more docker-compose services and the worker picks
the service with `switchPort(request, PORT)`, which writes the target port into
the `cf-container-target-port` request header
(`apps/digithings-stack-cloudflare/src/index.ts:153`). The shim reads that
header and forwards to the compose service on the host.

Resolution is keyed on **(class, port)**, never on port alone:
`DigiChatContainer` and `LangfuseWebContainer` both default to port 3000.

## Generate and run

```sh
# 1. compose services (profiles are named in the shim table)
docker compose up -d digigraph digikey digisearch digiquant

# 2. render the dev configs and entries
python3 scripts/selfhost/generate_dev_configs.py generate --write
python3 scripts/selfhost/generate_dev_configs.py table

# 3a. one multi-config session (what the plan asks for)
python3 scripts/selfhost/generate_dev_configs.py print-cmd --mode single

# 3b. one command per worker, each on its own fixed port
python3 scripts/selfhost/generate_dev_configs.py print-cmd --mode per-worker
```

Run each command from the repository root.

## Ports

| worker | dev port | role |
|---|---|---|
| digithings-stack | 8787 | primary (wrangler's default) |
| digichat | 8788 | auxiliary |
| dashboard-api | 8789 | auxiliary |
| digithings-cron | 8790 | `--test-scheduled` |
| digiquant-runner | 8791 | auxiliary |
| digitrace-langfuse | 8792 | auxiliary |

None of these collide with a published compose port; the test suite parses
`docker-compose.yml` and asserts that, so the table cannot drift silently.

## Which mode, and why

Cloudflare's [multi-worker development
docs](https://developers.cloudflare.com/workers/local-development/multi-workers/)
recommend a single `wrangler dev -c ... -c ...` session for binding
compatibility, and the plan asks for it, so `--mode single` is the default. One
constraint is documented and matters: **only the primary worker is exposed on an
HTTP URL**. The other five are reachable through service bindings, which is the
stated reason to prefer this mode, but you cannot `curl` them.

Service bindings also resolve across separate dev commands (Cloudflare changelog
2025-09-23, `wrangler-dev-multi-config-cross-command-support`), so
`--mode per-worker` is equivalent for binding resolution and is better when you
need a URL per worker. Each command in that mode still uses its own fixed port.

## What the transform changes, and what it must never change

Dropped from each generated config: `[[containers]]`,
`[[containers.authorized_keys]]`, `[[routes]]` (a local dev session must never
claim `digithings.ai`). Forced: `workers_dev = true`, written once at the top
level. Rewritten: `main` points at `.selfhost-dev/entry.ts`; container-backed
Durable Object classes become `SelfHost<Class>`; `[[migrations]]` drops container
names from `new_sqlite_classes`.

**A Durable Object that is not a container keeps its own name and its migration.**
`digithings-cron`'s `BackfillLedger` is a real SQLite DO; shimming it would
replace working state with a storageless class. That distinction is pinned by a
test.

## Known gaps (2026-10-10)

These container classes have **no compose service today**, so the shim answers
`503` naming the service that has to be added. It never guesses a port:

| class | container port | needed |
|---|---|---|
| `DigiQuantMcpContainer` | 8767 | `digiquant-mcp` publishing 8767 |
| `DigiQuantRunnerContainer` | 8080 | `digiquant-runner` publishing 8080 |
| `LangfuseWebContainer` | 3000 | `digitrace-langfuse-web` |
| `LangfuseWorkerContainer` | 3030 | `digitrace-langfuse-worker` |

`apps/digitrace-langfuse/docker-compose.local.yml` has only `clickhouse` and
`redis`; the Langfuse application containers themselves are not there.

Mapped today: `DigiStackContainer` (8000 digigraph, 8001 digiquant, 8002
digisearch, 8003 digitrace, 8004 digivault, 8005 digikey, 4000 litellm) and
`DigiChatContainer` (3000 -> host 3005, because compose publishes
`${DIGICHAT_PUBLISH_PORT:-3005}:3000`).

Analytics Engine has no Miniflare parity, so any worker that writes to it needs
a local stub. No worker in this slice declares an `[[analytics_engine]]` binding
today, so nothing is stubbed yet; slice S4 owns that surface.

## Not verified here

`wrangler dev` was not executed in the slice that wrote this: `node_modules` is
not installed in a fresh worktree. The transform and the routing table are
covered by tests; the session itself is documented, not run. Everything in
"Known gaps" was measured from `docker-compose.yml`, not from a live session.
