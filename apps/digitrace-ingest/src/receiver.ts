/**
 * The OTLP/HTTP receiver.
 *
 * `POST /v1/traces` in either OTLP/HTTP encoding (ADR-0036 §2). The order of the
 * checks is the security order, not a convenience order:
 *
 *   1. the path and the method, so nothing else is reachable;
 *   2. the token and the tenant claim, before a byte of the body is read, so an
 *      unauthenticated caller cannot spend the Worker's body budget;
 *   3. the declared and the actual body size, so an oversize body is refused
 *      rather than parsed;
 *   4. the encoding, then the parse.
 *
 * The tenant that reaches the queue is the one the token allows. The claimed
 * header never travels further than the check in `auth.ts`.
 */
import { authenticate, TENANT_HEADER, TOKEN_HEADER } from "./auth";
import { MAX_BODY_BYTES, respond } from "./respond";
import { chunkSpans } from "./chunk";
import { OtlpParseError, normalizeTraceRequest } from "./otlp-json";
import { decodeTraceRequest } from "./protobuf";
import { enqueue } from "./queue";
import { LAUNCH_SAMPLING_RATE, keepTrace } from "./sampling";
import type { Env, OtlpTraceRequest } from "./types";

export { MAX_BODY_BYTES };

export const TRACES_PATH = "/v1/traces";
export const HEALTH_PATH = "/health";

const JSON_TYPES = ["application/json", "application/otlp+json"];
const PROTOBUF_TYPES = ["application/x-protobuf", "application/protobuf"];

type Encoding = "json" | "protobuf";

export interface ReceiveDeps {
  /** Test seam for the receive timestamp and the archive date partition. */
  now?: () => Date;
  /** Test seam for the archive object name; production uses `crypto.randomUUID`. */
  newUuid?: () => string;
  /** Test seam for the sampling rate; production is `LAUNCH_SAMPLING_RATE`. */
  samplingRate?: number;
}

/** The OTLP encoding of a request, or undefined when it is not one we accept. */
export function encodingOf(contentType: string | null): Encoding | undefined {
  const base = (contentType ?? "").split(";")[0].trim().toLowerCase();
  if (JSON_TYPES.includes(base)) return "json";
  if (PROTOBUF_TYPES.includes(base)) return "protobuf";
  return undefined;
}

async function readBody(request: Request): Promise<Uint8Array> {
  const declared = request.headers.get("content-length");
  if (declared !== null) {
    const length = Number(declared);
    if (Number.isFinite(length) && length > MAX_BODY_BYTES) {
      throw new BodyTooLarge();
    }
  }

  const raw = new Uint8Array(await request.arrayBuffer());
  if (raw.byteLength > MAX_BODY_BYTES) throw new BodyTooLarge();

  const encoding = (request.headers.get("content-encoding") ?? "").trim().toLowerCase();
  if (encoding === "" || encoding === "identity") return raw;
  if (encoding !== "gzip") throw new UnsupportedEncoding(encoding);

  return inflate(raw);
}

/**
 * Gunzip with the cap applied *while* inflating.
 *
 * The cap applies to what is parsed, not only to what arrived: a gzip bomb is
 * small on the wire and enormous after inflating. Reading the whole expansion
 * into an ArrayBuffer first would spend the isolate's memory before the check
 * could refuse it, so the stream is counted chunk by chunk and abandoned the
 * moment it passes the cap.
 */
async function inflate(raw: Uint8Array): Promise<Uint8Array> {
  const reader = new Blob([raw]).stream().pipeThrough(new DecompressionStream("gzip")).getReader();
  const parts: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      total += value.byteLength;
      if (total > MAX_BODY_BYTES) {
        await reader.cancel();
        throw new BodyTooLarge();
      }
      parts.push(value);
    }
  } catch (error) {
    if (error instanceof BodyTooLarge) throw error;
    throw new InvalidBody("body is not valid gzip");
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.byteLength;
  }
  return out;
}

class BodyTooLarge extends Error {}
/** A body that arrived in the declared encoding but does not decode in it. */
class InvalidBody extends Error {}
class UnsupportedEncoding extends Error {
  constructor(readonly encoding: string) {
    super(`unsupported content-encoding ${encoding}`);
  }
}

function parseBody(bytes: Uint8Array, encoding: Encoding): OtlpTraceRequest {
  if (encoding === "json") {
    let parsed: unknown;
    try {
      parsed = JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      throw new OtlpParseError("body is not valid JSON");
    }
    return parsed as OtlpTraceRequest;
  }
  return decodeTraceRequest(bytes);
}

/** `POST /v1/traces`, and the health probe. */
export async function handleRequest(
  request: Request,
  env: Env,
  deps: ReceiveDeps = {},
): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === HEALTH_PATH) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return respond.json(405, { error: "method not allowed" }, { allow: "GET, HEAD" });
    }
    return respond.json(200, { ok: true, service: "digitrace-ingest" });
  }

  if (url.pathname !== TRACES_PATH) {
    return respond.json(404, { error: "not found" });
  }
  if (request.method !== "POST") {
    return respond.json(405, { error: "method not allowed" }, { allow: "POST" });
  }

  const auth = await authenticate(
    env.INGEST_TOKENS,
    request.headers.get(TOKEN_HEADER),
    request.headers.get(TENANT_HEADER),
  );
  if (!auth.ok) {
    return respond.json(auth.status, { error: auth.reason });
  }

  const encoding = encodingOf(request.headers.get("content-type"));
  if (encoding === undefined) {
    return respond.json(415, {
      error: "content-type must be application/json or application/x-protobuf",
    });
  }

  let bytes: Uint8Array;
  try {
    bytes = await readBody(request);
  } catch (error) {
    if (error instanceof BodyTooLarge) {
      return respond.json(413, { error: `body exceeds ${MAX_BODY_BYTES} bytes` });
    }
    if (error instanceof UnsupportedEncoding) {
      return respond.json(415, { error: "content-encoding must be gzip or absent" });
    }
    if (error instanceof InvalidBody) {
      return respond.json(400, { error: error.message });
    }
    throw error;
  }

  let records;
  let rejectedSpans: number;
  try {
    const normalized = normalizeTraceRequest(parseBody(bytes, encoding));
    records = normalized.records;
    rejectedSpans = normalized.rejectedSpans;
  } catch (error) {
    if (error instanceof OtlpParseError) {
      // The message describes the envelope, never the body: a parse error must
      // not echo span content back to a caller. A protobuf source gets a
      // protobuf response, because it decodes what it sent.
      return respond.error(encoding, 400, `invalid OTLP trace request: ${error.message}`);
    }
    throw error;
  }

  const rate = deps.samplingRate ?? LAUNCH_SAMPLING_RATE;
  const kept = records.filter((record) => keepTrace(record.span.traceId, rate));

  const now = (deps.now ?? (() => new Date()))();
  const { messages, droppedOversizedSpans } = chunkSpans(
    kept,
    {
      batchId: crypto.randomUUID(),
      tenant: auth.context.tenant,
      tenantSlugVerified: auth.context.tenantSlugVerified,
      source: auth.context.source,
      receivedAt: now.toISOString(),
    },
    deps.newUuid,
  );

  if (messages.length > 0) {
    try {
      await enqueue(env.INGEST_QUEUE, messages);
    } catch {
      // 503, not 500: the source should retry this request. The message says
      // nothing about the queue's internals.
      return respond.error(encoding, 503, "ingest queue is unavailable, retry the request");
    }
  }

  return respond.success(encoding, rejectedSpans + droppedOversizedSpans);
}
