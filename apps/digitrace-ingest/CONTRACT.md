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

## 5. The index rows (Supabase `core`, schema `public`)

The consumer resolves `workspaces.id` from the verified tenant slug over PostgREST
and stamps `workspace_id` on every row. **`tenant_slug` is not an index column**
(ADR-0036 §5): the index has one tenancy column and it is `workspace_id`.

Every row is a pure function of the queue message plus the resolved
`workspace_id`, so a retried message writes identical rows. Upserts use the
natural key below.

### `digitrace_spans_index` — one row per span

Conflict target: `workspace_id,trace_id,span_id`.

| Column           | Type               | Source                                                       |
| ---------------- | ------------------ | ------------------------------------------------------------ |
| `workspace_id`   | `uuid`             | resolved from `workspaces.slug`                              |
| `trace_id`       | `text`             | hex, 32 chars                                                |
| `span_id`        | `text`             | hex, 16 chars                                                |
| `parent_span_id` | `text` null        | hex, or null for a root                                      |
| `name`           | `text`             | `span.name`                                                  |
| `kind`           | `text`             | enum name, e.g. `SPAN_KIND_SERVER`                           |
| `status_code`    | `text`             | `STATUS_CODE_UNSET` / `STATUS_CODE_OK` / `STATUS_CODE_ERROR` |
| `status_message` | `text` null        | `span.status.message`                                        |
| `started_at`     | `timestamptz` null | from `startTimeUnixNano`                                     |
| `ended_at`       | `timestamptz` null | from `endTimeUnixNano`                                       |
| `duration_ms`    | `integer` null     | end − start                                                  |
| `service_name`   | `text` null        | resource `service.name`                                      |
| `scope_name`     | `text` null        | `scope.name`                                                 |
| `model`          | `text` null        | `gen_ai.*.model`, `llm.model_name`                           |
| `input_tokens`   | `integer` null     | `gen_ai.usage.input_tokens`, `llm.token_count.prompt`        |
| `output_tokens`  | `integer` null     | `gen_ai.usage.output_tokens`, `llm.token_count.completion`   |
| `attributes`     | `jsonb`            | the span's attributes as a flat object                       |
| `events`         | `jsonb`            | the span's events, unchanged                                 |
| `received_at`    | `timestamptz`      | the queue message's receive time                             |

### `digitrace_traces` — one row per trace id in the batch

Conflict target: `workspace_id,trace_id`.

| Column                           | Type               | Source                                                      |
| -------------------------------- | ------------------ | ----------------------------------------------------------- |
| `workspace_id`                   | `uuid`             | resolved                                                    |
| `trace_id`                       | `text`             | hex                                                         |
| `root_span_name`                 | `text`             | the span with no parent, else the first in the batch        |
| `root_service_name`              | `text` null        | that span's resource `service.name`                         |
| `started_at` / `ended_at`        | `timestamptz` null | min start / max end across the batch                        |
| `duration_ms`                    | `integer` null     | end − start                                                 |
| `span_count`                     | `integer`          | spans of this trace in the batch                            |
| `error_count`                    | `integer`          | spans with an error status or an exception event            |
| `status_code`                    | `text`             | `STATUS_CODE_ERROR` when `error_count > 0`, else the root's |
| `session_id`                     | `text` null        | first session id found on the trace                         |
| `model`                          | `text` null        | first model found on the trace                              |
| `input_tokens` / `output_tokens` | `integer`          | summed across the trace's spans                             |
| `received_at`                    | `timestamptz`      | receive time                                                |

### `digitrace_sessions` — one row per session id in the batch

Conflict target: `workspace_id,session_id`.

| Column                           | Type               | Source                                                   |
| -------------------------------- | ------------------ | -------------------------------------------------------- |
| `workspace_id`                   | `uuid`             | resolved                                                 |
| `session_id`                     | `text`             | `session.id`, `gen_ai.conversation.id`, `llm.session_id` |
| `first_seen_at` / `last_seen_at` | `timestamptz` null | min start / max end of the spans that carry it           |
| `received_at`                    | `timestamptz`      | receive time                                             |

### `digitrace_scores`

**Not written by this Worker.** ADR-0036 §4 and §8 put the score write-back in
MLflow: it writes to `public.digitrace_scores` through the service role.

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

## 7. Human steps (prepared, not performed)

- [ ] Confirm the account is on Workers Paid — Queues needs it.
- [ ] Create the R2 bucket `digitrace-archive`, and its 180-day lifecycle rule.
- [ ] Create the Queue `digitrace-ingest` and the dead-letter queue `digitrace-ingest-dlq`.
- [ ] Create the KV namespace, put its id in `wrangler.toml`, and add one record per
      source under `tok:<sha256 of the token>`.
- [ ] Create the Analytics Engine dataset `digitrace_ingest`.
- [ ] `wrangler secret put CORE_SUPABASE_SERVICE_KEY`.
- [ ] Create the DNS record for `trace.digithings.ai`, uncomment the route in
      `wrangler.toml`, and approve the production deploy.

## 8. Not in scope here

- The index migration and the RLS policies: **DIG-2658**.
- Turning the emitters on: **DIG-2659** (Workers) and **DIG-2660** (GitHub Actions).
- Hyperdrive: **DIG-2658** decides. This Worker uses PostgREST only.
- The dashboard Traces tab (**DIG-2661**) and `digitrace replay` (**DIG-2662**).
