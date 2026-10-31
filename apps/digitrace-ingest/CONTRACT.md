# digitrace-ingest — contract

The wire and storage contract of the digitrace OTLP/HTTP ingest path. ADR-0036 is
the decision; this file is the implementation's exact shape, because two sibling
leaves (DIG-2658, the index migration; DIG-2659/DIG-2660, the emitters) build
against it at the same time.

## 1. The route

|                |                                                                             |
| -------------- | --------------------------------------------------------------------------- |
| Method         | `POST`                                                                      |
| Path           | `/v1/traces`                                                                |
| Host (planned) | `trace.digithings.ai` — the custom domain is a human step (§7)              |
| Encodings      | `application/json` (OTLP/JSON) and `application/x-protobuf` (OTLP/protobuf) |
| Compression    | `content-encoding: gzip` accepted; anything else is `415`                   |
| Body cap       | 4 MiB, checked on the declared length and on the actual bytes               |
| Probe          | `GET /health` → `{"ok":true,"service":"digitrace-ingest"}`                  |

The response encoding follows the request encoding. A protobuf source gets a
protobuf `ExportTraceServiceResponse`, because a client decodes what it sent.

## 2. The two headers

| Header               | Required | Meaning                                                                                                                           |
| -------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `x-digitrace-token`  | yes      | Per-source static credential. A Worker secret is **not** used: the token lives in KV so one namespace holds one entry per source. |
| `x-digitrace-tenant` | yes      | The tenant slug the source claims, `^[a-z0-9][a-z0-9-]{0,62}$`.                                                                   |

The KV record:

```
key   = tok:<sha256 hex of the token>
value = {"source":"digitrace-digichat","tenants":["digithings"]}
```

The key is the token's digest, so the namespace never holds a usable credential.
`source` is what the index and the archive record; a request cannot set it.

**Resolution and refusal.** The Worker looks the token up, then checks the claimed
slug against the record's `tenants` list:

| Condition                                                           | Status |
| ------------------------------------------------------------------- | ------ |
| no token / unknown token                                            | `401`  |
| no tenant claim, malformed slug, or a slug this token may not claim | `403`  |

A refused batch is dropped, not repaired. The tenant that reaches the queue is the
verified slug from the token record; nothing the client sends can name a different
one.

`tenant_slug_verified` is **false** on this path. ADR-0036 §2 records the
deviation from digikey: the flag is true only for a claim inside a digikey-signed
JWT, which this endpoint does not accept. The value is stored either way.

## 3. The archive object (R2)

Bucket `digitrace-archive`.

```
tenant=<slug>/date=<YYYY-MM-DD>/<source>/<uuid>.ndjson
```

- `date` is the **UTC** calendar date of the receive time.
- `uuid` is generated at receive time and carried in the queue message, so a queue
  retry rewrites the same object instead of creating a duplicate.
- One object per queue message. One request becomes as many objects as it takes to
  fit the queue's 128 KiB message ceiling; every object carries the same
  `batch_id`, its own `chunk` index and the total `chunks`.

Body: one JSON line per span, newline-terminated.

```json
{"tenant_slug":"digithings","tenant_slug_verified":false,"source":"digitrace-digichat","batch_id":"…","chunk":0,"chunks":1,"received_at":"2026-10-26T12:34:56.000Z","resource":{…},"scope":{…},"span":{…}}
```

`resource`, `scope` and `span` are the OTLP/JSON shapes. A protobuf source is
decoded into the same shapes, so the archive has one format whatever the source
sent. Trace and span ids are lowercase hex in both cases.

R2 custom metadata on each object: `tenant`, `tenant_slug_verified`, `source`,
`batch_id`, `chunk` (`"0/1"` form).

## 4. The queue message

```json
{
  "v": 1,
  "batchId": "…",
  "chunk": 0,
  "chunks": 1,
  "tenant": "digithings",
  "tenantSlugVerified": false,
  "source": "digitrace-digichat",
  "receivedAt": "2026-10-26T12:34:56.000Z",
  "archiveKey": "tenant=digithings/date=2026-10-26/digitrace-digichat/<uuid>.ndjson",
  "ndjson": "…"
}
```

The consumer refuses a message whose `archiveKey` is not under its own
`tenant=` prefix: a tampered message cannot write into another tenant's partition.
A message that cannot parse is acknowledged and logged, never retried.

Retry policy: `max_retries = 5`, `dead_letter_queue = "digitrace-ingest-dlq"`, and
a per-message back-off of `min(15s × 2^(attempts−1), 300s)`.

## 5. The index rows (D1 `digitrace`, binding `INDEX_DB`)

DIG-2887 S1 moved the index from the core Postgres project to its own D1 database.
`workspace_id` holds the **verified tenant slug** (D1 has no `workspaces` table to
resolve an id from), and the consumer stamps it on every row. **`tenant_slug` is not
written** (ADR-0036 §5): the index has one tenancy column and it is `workspace_id`.
D1 has no row-level security and is reachable only through the binding, so the
tenant boundary is the `workspace_id` filter in Worker code.

The consumer writes **two** tables. The column names below are those of
`migrations/0001_digitrace_index.sql` (the SQLite port of DIG-2658's schema), not
an independent guess — a name that does not exist there fails the first real batch.

Every row is a pure function of the queue message plus the resolved
`workspace_id`, so a retried message writes identical rows.

### `digitrace_spans_index` — one row per span

Conflict target: `workspace_id,trace_id,span_id`.

| Column                                                       | Source                                                                                             |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `workspace_id`                                               | resolved from `workspaces.slug`                                                                    |
| `trace_id`, `span_id`, `parent_span_id`                      | hex ids; `parent_span_id` null for a root                                                          |
| `name`                                                       | `span.name`                                                                                        |
| `kind`                                                       | enum name, e.g. `SPAN_KIND_SERVER`                                                                 |
| `started_at`                                                 | `startTimeUnixNano`; **receive time when the span carries none**, because the column is `NOT NULL` |
| `ended_at`                                                   | `endTimeUnixNano`                                                                                  |
| `duration_ms`                                                | end − start, null when either is missing                                                           |
| `status`, `status_message`                                   | the status enum name and message                                                                   |
| `session_id`                                                 | `session.id`, `digi.session_id`                                                                    |
| `run_id`                                                     | `pipeline.run_id`, `digi.workflow_id`, `digi.run_name`                                             |
| `model`                                                      | `gen_ai.response.model`, `gen_ai.request.model`, `llm.model_name`                                  |
| `provider`                                                   | `gen_ai.provider.name`, `gen_ai.system`, `llm.provider`                                            |
| `input_tokens`, `output_tokens`                              | `gen_ai.usage.*`, `llm.token_count.*`                                                              |
| `total_tokens`                                               | `gen_ai.usage.total_tokens`, `llm.token_count.total`, else input + output                          |
| `cost_usd`                                                   | `digitrace.cost_usd`, `llm.cost.total`, `gen_ai.usage.cost` (never computed here)                  |
| `input_hash`, `input_length`, `output_hash`, `output_length` | `digi.*.sha256` / `digi.*.length` (DIG-2656)                                                       |
| `attributes`                                                 | the **allowlisted** span attributes as a flat JSON object                                          |

Span **events** stay in the archive only: the index has no column for them.

### `digitrace_traces` — one row per trace id in the message

Conflict target: `workspace_id,trace_id`.

The row is a **cross-span aggregate**, and an upsert replaces it: the later
message's row wins outright. Two things keep it true:

1. `chunkSpans` packs whole traces, so a message boundary does not fall inside a
   trace; a trace that alone exceeds the 56 KiB budget still crosses one and is
   listed in the message's `incompleteTraces`.
2. After the spans are written, the consumer runs `REFRESH_TRACE_SQL`
   (`src/d1.ts`) for every trace in the message. It is **UPDATE-only**, so the insert
   from this message is what creates the row; the call then recomputes
   `span_count`, the time window, `duration_ms`, the root `name`, a sticky error
   status and the first `session_id`/`run_id` over **every** row of
   `digitrace_spans_index` for that trace.

The second step is what makes a split trace and a trace exported across **several
OTLP requests** converge: each slice inserts its spans, then recomputes from all
of them. The recompute is one `UPDATE … FROM` statement and D1 serialises writes,
so two slices in flight at once cannot interleave inside it. The trade is one
statement per trace in a message (a message usually carries one trace per OTLP
request). The span rows of a message are written as one `batch()`, which D1 runs
as a single transaction.

| Column                 | Source                                                                           |
| ---------------------- | -------------------------------------------------------------------------------- |
| `workspace_id`         | resolved                                                                         |
| `source`               | the token's source — never the client's word                                     |
| `trace_id`             | hex                                                                              |
| `name`                 | the root span (the recompute); the insert falls back to the first span           |
| `service_name`         | that span's resource `service.name`                                              |
| `started_at`           | min start over the trace, **receive time when nothing carries one** (`NOT NULL`) |
| `ended_at`             | max end over the trace, `NULL` while any span of it is still open                |
| `duration_ms`          | end − start                                                                      |
| `status`               | `STATUS_CODE_ERROR` when any span failed, else the root's                        |
| `status_message`       | the first failed span's message (the root's when nothing failed)                 |
| `session_id`, `run_id` | first correlation id found on the trace                                          |
| `attributes`           | the root span's allowlisted attributes                                           |
| `resource`             | the root resource's allowlisted attributes                                       |
| `span_count`           | spans of the trace, from the recompute (the insert writes this message's count)  |

### `digitrace_sessions` — not written by this consumer

The table's `trace_count`, `span_count`, `total_tokens` and `total_cost_usd` are
**cross-batch** aggregates, and an upsert can only replace them: the second batch
of a session would overwrite a larger count with a smaller one. The ingest path
leaves the table alone rather than write numbers that silently shrink. A session
recompute (the counterpart of the trace recompute) is a separate change.

### `digitrace_scores` — not written by this consumer

ADR-0036 §4 and §8 put the score write-back in MLflow. The table now lives in D1,
so that write-back needs a D1 path (a Worker endpoint or the D1 HTTP API); it is
not wired yet.

### What may reach `attributes`

An explicit allowlist (`INDEX_ATTRIBUTE_ALLOWLIST` in `src/attributes.ts`), which
is DIG-2656's emitter allowlist minus the two `digi.*.preview` keys. A preview is
content, it is opt-in at the source, and the index is not where content goes
(ADR-0036 §7). Everything else the source sent still reaches the archive untouched.

## 6. The Analytics Engine point

Dataset `digitrace_ingest`, one point per span.

|           | Values                                                             |
| --------- | ------------------------------------------------------------------ |
| `indexes` | `[tenant]`                                                         |
| `blobs`   | `tenant`, `source`, `service_name`, `model`, `status_code`, `kind` |
| `doubles` | `input_tokens`, `output_tokens`, `duration_ms`, `cost_usd`, `1`    |

`cost_usd` is carried only when the source computed it
(`digitrace.cost_usd`, `llm.cost.total`, `gen_ai.usage.cost`); this Worker does not
price a model. A write failure is swallowed: the aggregates are an estimate
(ADR-0036 §3), and the archive is the record.

One known limit: Analytics Engine has no idempotency key, so a queue retry
re-writes the same point and a retried message double-counts its tokens and cost.
The point is per span because that is the shape the estimate needs; a batch-level
write that a retry cannot duplicate is the WAE spike on DIG-2661.

## 7. Human steps (prepared, not performed)

- [ ] Confirm the account is on Workers Paid — Queues needs it.
- [ ] Create the R2 bucket `digitrace-archive`, and its 180-day lifecycle rule.
- [ ] Create the Queue `digitrace-ingest` and the dead-letter queue `digitrace-ingest-dlq`.
- [ ] Create the KV namespace, put its id in `wrangler.toml`, and add one record per
      source under `tok:<sha256 of the token>`.
- [ ] Create the Analytics Engine dataset `digitrace_ingest`.
- [ ] `wrangler d1 create digitrace` and put its id in `wrangler.toml`. The deploy
      workflow applies `migrations/` before every deploy, and skips the deploy
      while any id in `wrangler.toml` is still the all-zero placeholder.
- [ ] Create the DNS record for `trace.digithings.ai`, uncomment the route in
      `wrangler.toml`, and approve the production deploy.

## 8. Not in scope here

- The index migration and the RLS policies: **DIG-2658**.
- Turning the emitters on: **DIG-2659** (Workers) and **DIG-2660** (GitHub Actions).
- Retention: a 90-day prune of the D1 index needs a cron trigger (human step).
- The dashboard Traces tab (**DIG-2661**) and `digitrace replay` (**DIG-2662**).
