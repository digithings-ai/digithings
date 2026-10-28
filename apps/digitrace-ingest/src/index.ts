/**
 * apps/digitrace-ingest — the digitrace OTLP/HTTP ingest path (DIG-2657).
 *
 * One Worker, two entry points (ADR-0036 §1):
 *   fetch — `POST /v1/traces`, the OTLP/HTTP receiver. Per-source token, tenant
 *           resolved server-side, both OTLP encodings, size cap, sampling.
 *   queue — the consumer. Archive object in R2, index rows in D1, metric
 *           points in Workers Analytics Engine.
 *
 * The receiver refuses an unknown token, a tenant the token may not claim, a
 * body it cannot parse, and a body over the cap. The consumer retries a failed
 * message and lets the Queue's `max_retries` and dead-letter queue bound it.
 *
 * Contract: `CONTRACT.md` in this directory. Human steps: `wrangler.toml`.
 */
import { handleQueue } from "./consumer";
import { handleRequest } from "./receiver";
import type { Env, IngestMessage } from "./types";

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },

  queue(batch: MessageBatch<IngestMessage>, env: Env): Promise<void> {
    return handleQueue(batch, env);
  },
};

export { handleRequest } from "./receiver";
export { handleQueue } from "./consumer";
