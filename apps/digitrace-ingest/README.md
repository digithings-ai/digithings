# digitrace-ingest

The OTLP/HTTP ingest path for digitrace: a Cloudflare Worker that receives traces,
queues them, and fans the batch out to an R2 archive, a Supabase index and Workers
Analytics Engine. Design: [ADR-0036](../../docs/adr/0036-digitrace-cloudflare-native-tracing.md);
exact shapes: [`CONTRACT.md`](./CONTRACT.md).

```
source ──POST /v1/traces──▶ fetch  ──▶ Queue ──▶ queue ──┬─▶ R2  digitrace-archive
        (token + tenant)                                  ├─▶ Supabase core.public.digitrace_*
                                                          └─▶ Analytics Engine digitrace_ingest
```

## What the receiver refuses

| Condition                                                        | Status                     |
| ---------------------------------------------------------------- | -------------------------- |
| unknown or missing `x-digitrace-token`                           | `401`                      |
| missing claim, malformed slug, or a slug the token may not claim | `403`                      |
| `content-type` that is not OTLP JSON or protobuf                 | `415`                      |
| `content-encoding` that is not `gzip`                            | `415`                      |
| body over 4 MiB (declared or actual, and after inflating)        | `413`                      |
| a body that is not an OTLP trace export envelope                 | `400`                      |
| the queue refusing the batch                                     | `503` (the source retries) |

A malformed _span_ does not fail the batch: it is dropped and counted in the OTLP
`partialSuccess` response, so a loss is visible to the source rather than silent.
A span too large for one 128 KiB queue message is the only other loss, and it is
counted the same way.

## Why this shape

- **One Worker, two entry points.** `fetch` receives, `queue` stores. The queue
  decouples the source's latency from the sinks' latency, and gives the retry and
  dead-letter behaviour for free.
- **The tenant comes from the token.** The claimed slug is checked against the
  token's tenant list; a rejected batch is dropped, not repaired. Nothing the
  client sends can name the tenant that is stored.
- **The archive is the system of record.** R2 is written first and the index
  second, so a failed index write is a retry, not a lost trace.
- **Both OTLP encodings.** The Cloudflare destinations send JSON; the Python and
  GitHub Actions sources send protobuf. The protobuf decoder is a small,
  hand-written subset of the trace export grammar (`src/protobuf.ts`) rather than
  a general runtime and the generated descriptors; an unknown field number is
  skipped, as the spec requires.
- **Retries are per message, not per batch.** One poison message cannot send its
  healthy neighbours back through the queue. `max_retries = 5` and
  `digitrace-ingest-dlq` bound the rest.
- **Analytics Engine is best-effort.** A metric write never fails a stored batch;
  the aggregates are an estimate by contract.
- **The index is written to the schema DIG-2658 ships**, table by table, and the
  consumer writes two of the four tables: `digitrace_sessions` carries cross-batch
  counters that a REST upsert can only overwrite, and `digitrace_scores` is
  MLflow's write-back. [`CONTRACT.md` §5](./CONTRACT.md) says why, per column.

## Local development

```sh
npm install                       # from the repo root
cd apps/digitrace-ingest
npm run dev                       # wrangler dev, local bindings
npm run test                      # vitest
npm run typecheck                 # tsc --noEmit
npx wrangler deploy --dry-run     # what the PR gate runs
```

`wrangler dev` runs with local R2, KV and Queue bindings. To exercise the receiver
locally, put one token record in the local KV namespace and send a request. Keep
the token in a shell variable so no literal ever sits after a header name — a
literal there reads as a credential to the secrets scanner, whether or not it is
one:

```sh
# Throwaway token for the local emulator. Not a secret, and never deployed.
export DIGITRACE_INGEST_TOKEN=local-dev-token

npx wrangler kv key put --binding INGEST_TOKENS \
  "tok:$(printf '%s' "$DIGITRACE_INGEST_TOKEN" | shasum -a 256 | cut -d' ' -f1)" \
  '{"source":"digitrace-digichat","tenants":["digithings"]}' --local

curl -sS -X POST http://localhost:8787/v1/traces \
  -H "x-digitrace-token: $DIGITRACE_INGEST_TOKEN" \
  -H 'x-digitrace-tenant: digithings' \
  -H 'content-type: application/json' \
  --data '{"resourceSpans":[]}'
```

Never put a real token in a command you paste into an issue, a log or a PR, and
never assign one to a variable in a file that is committed.

## Tests

`npm test` — 165 tests over the receiver, the protobuf decoder, the chunker, the
queue grouping, the consumer and its retry policy, the index rows, the metric
points, the PostgREST client, the token check, sampling, and the deployment
contract in `wrangler.toml`. The suite is plain Node: bindings are fakes, because
what is under test is this Worker's decisions, not Miniflare.

## Deployment

`.github/workflows/deploy-digitrace-ingest.yml`, on `main`, behind the
`production` environment gate. The first deploy needs the human steps in
[`CONTRACT.md` §7](./CONTRACT.md) — the bucket, the queue and its dead-letter
queue, the KV namespace, the Analytics Engine dataset, the secret, the DNS record
and the route. The route and the public hostname are a human step (ADR-0036 §15).
