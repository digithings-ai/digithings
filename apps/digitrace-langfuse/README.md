# digitrace Langfuse (Cloudflare Containers)

Phase 1 stand-up for **self-hosted Langfuse** behind digitrace (#4930).

- **Langfuse Web** — UI, REST API, OTLP ingest (`/api/public/otel`) on `:3000`
- **Langfuse Worker** — background queues on `:3030` (not publicly routed)
- **Postgres** — `DATABASE_URL` → dedicated DB on house Postgres (secret put)
- **R2** — event bucket `digitrace-langfuse-events` via `LANGFUSE_S3_EVENT_UPLOAD_*`
- **ClickHouse + Redis** — **external** managed/VM only (never a lite CF Container for CH)

Images are pinned: `langfuse/langfuse:4.49.0` and `langfuse/langfuse-worker:4.49.0`
(`Dockerfile.digitrace-langfuse-web` / `Dockerfile.digitrace-langfuse-worker` at repo root).

Full operator runbook: [`docs/ops/digitrace-langfuse.md`](../../docs/ops/digitrace-langfuse.md).  
Lab swap memo: [`docs/plans/digitrace-langfuse-swap-2026-10-01.md`](../../docs/plans/digitrace-langfuse-swap-2026-10-01.md).

## Hostname (HUMAN GATE)

Preferred public hostname: **`trace.digithings.ai`**.

The custom-domain `[[routes]]` entry in `wrangler.toml` is **commented out** until
Platform approves DNS and secret puts. Do not enable a guessable `*.workers.dev`
front (`workers_dev = false`).

Alternate name `langfuse.digithings.ai` is acceptable if DNS prefers it — pick one
and keep `NEXTAUTH_URL` in lockstep.

## Prerequisites

- Workers Paid (Containers)
- Docker available for `wrangler deploy` image build
- House Postgres: create dedicated database (e.g. `langfuse`) — see runbook
- R2 bucket `digitrace-langfuse-events` + S3 API token (human)
- Managed ClickHouse (~2 CPU / 8 GiB **minimum**) + Redis (human)
- `npx wrangler login` on the digithings Cloudflare account

## Deploy (after human secrets)

```bash
cd apps/digitrace-langfuse
npm install

# See docs/ops/digitrace-langfuse.md for the full secret put checklist.
npx wrangler secret put DATABASE_URL
# … remaining secrets …

npx wrangler deploy
# Wake the queue Worker once after deploy:
curl -sS "https://trace.digithings.ai/_langfuse/worker-wake"
```

## Edge paths

| Path | Behavior |
|------|----------|
| `/_langfuse/healthz` | Worker-only liveness JSON |
| `/_langfuse/worker-wake` | Best-effort wake of Langfuse Worker Container |
| everything else | Proxied to Langfuse Web Container |

## Smoke

### UI login (manual)

1. Open `https://trace.digithings.ai` (or chosen hostname).
2. Complete first-user / org signup (Langfuse first-boot).
3. Create a project; copy public key + secret key (Basic auth for OTLP).

### OTLP (script)

```bash
export DIGITRACE_LANGFUSE_OTLP_ENDPOINT="https://trace.digithings.ai/api/public/otel"
# Basic auth header value only — never commit. Prefer Digi header env:
export DIGI_OTEL_HEADERS="Authorization=Basic <base64(public:secret)>"
bash scripts/smoke_digitrace_langfuse_otlp.sh
```

Uses `#4927` header resolution (`DIGI_OTEL_HEADERS` / `OTEL_EXPORTER_OTLP_HEADERS`).
Do **not** point `LANGSMITH_ENDPOINT` at Langfuse.

## Out of scope (later phases)

- Dual-export beside LangSmith (Phase 2)
- Cut LangSmith / Task 7 remap (Phases 3–4)
- DigiQuant clocks / DigiVoice
