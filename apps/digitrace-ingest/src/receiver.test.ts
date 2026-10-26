import { describe, expect, it } from "vitest";
import { tokenKey } from "./auth";
import { handleRequest, MAX_BODY_BYTES } from "./receiver";
import { testEnv, otlpJsonRequest, type TestEnv } from "../test/fakes";

const TOKEN = "token-for-receiver-tests";
const ENDPOINT = "https://trace.digithings.ai/v1/traces";

async function envWithToken(
  record: { source: string; tenants: string[] } = {
    source: "digitrace-digichat",
    tenants: ["digithings"],
  },
  options: Parameters<typeof testEnv>[0] = {},
): Promise<TestEnv> {
  return testEnv({
    ...options,
    tokens: { [await tokenKey(TOKEN)]: JSON.stringify(record) },
  });
}

function request(
  body: BodyInit | null,
  headers: Record<string, string> = {},
  options: { method?: string; url?: string } = {},
): Request {
  return new Request(options.url ?? ENDPOINT, {
    method: options.method ?? "POST",
    headers: {
      "x-digitrace-token": TOKEN,
      "x-digitrace-tenant": "digithings",
      "content-type": "application/json",
      ...headers,
    },
    body: options.method === "GET" || options.method === "HEAD" ? null : body,
  });
}

const FIXED_NOW = new Date("2026-10-26T12:34:56.000Z");

describe("POST /v1/traces, JSON", () => {
  it("accepts a batch and enqueues one archive message", async () => {
    const env = await envWithToken();
    const response = await handleRequest(request(JSON.stringify(otlpJsonRequest())), env, {
      now: () => FIXED_NOW,
      newUuid: () => "uuid-1",
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/json");
    expect(await response.json()).toEqual({});

    expect(env.__queue.sent).toHaveLength(1);
    const [message] = env.__queue.sent;
    expect(message).toMatchObject({
      v: 1,
      chunk: 0,
      chunks: 1,
      tenant: "digithings",
      tenantSlugVerified: false,
      source: "digitrace-digichat",
      receivedAt: "2026-10-26T12:34:56.000Z",
      archiveKey: "tenant=digithings/date=2026-10-26/digitrace-digichat/uuid-1.ndjson",
    });

    const lines = message.ndjson
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({
      tenant_slug: "digithings",
      tenant_slug_verified: false,
      source: "digitrace-digichat",
      batch_id: message.batchId,
      chunk: 0,
      chunks: 1,
      received_at: "2026-10-26T12:34:56.000Z",
    });
    expect(lines[0].span.name).toBe("GET /chat");
    expect(lines[0].span.traceId).toBe("0af7651916cd43dd8448eb211c80319c");
    expect(lines[0].resource.attributes[0].key).toBe("service.name");
  });

  it("uses the verified tenant, never a tenant the body mentions", async () => {
    const env = await envWithToken();
    const body = otlpJsonRequest({
      resourceAttributes: [
        { key: "service.name", value: { stringValue: "digitrace-test" } },
        { key: "tenant.id", value: { stringValue: "another-tenant" } },
      ],
    });
    await handleRequest(request(JSON.stringify(body)), env, { now: () => FIXED_NOW });

    const [message] = env.__queue.sent;
    expect(message.tenant).toBe("digithings");
    expect(message.archiveKey.startsWith("tenant=digithings/")).toBe(true);
    const line = JSON.parse(message.ndjson.trim());
    expect(line.tenant_slug).toBe("digithings");
  });

  it("refuses a tenant claim the token may not write for, and enqueues nothing", async () => {
    const env = await envWithToken();
    const response = await handleRequest(
      request(JSON.stringify(otlpJsonRequest()), { "x-digitrace-tenant": "occ" }),
      env,
    );

    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({
      error: "tenant claim is not allowed for this token",
    });
    expect(env.__queue.sent).toHaveLength(0);
  });

  it("refuses an unknown token with 401 and does not read the body", async () => {
    const env = await envWithToken();
    const response = await handleRequest(
      request("this is not even otlp", { "x-digitrace-token": "wrong" }),
      env,
    );
    expect(response.status).toBe(401);
    expect(env.__queue.sent).toHaveLength(0);
    expect(JSON.stringify(await response.json())).not.toContain("wrong");
  });

  it("refuses a request with no token header at all", async () => {
    const env = await envWithToken();
    const withoutToken = new Request(ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json", "x-digitrace-tenant": "digithings" },
      body: JSON.stringify(otlpJsonRequest()),
    });
    expect((await handleRequest(withoutToken, env)).status).toBe(401);
  });

  it("refuses a body over the cap with 413, before parsing it", async () => {
    const env = await envWithToken();
    const oversized = "a".repeat(MAX_BODY_BYTES + 1);
    const response = await handleRequest(request(oversized), env);
    expect(response.status).toBe(413);
    expect(await response.json()).toEqual({
      error: `body exceeds ${MAX_BODY_BYTES} bytes`,
    });
    expect(env.__queue.sent).toHaveLength(0);
  });

  it("accepts exactly the cap", async () => {
    const env = await envWithToken();
    const padding = " ".repeat(
      MAX_BODY_BYTES - Buffer.byteLength(JSON.stringify(otlpJsonRequest())),
    );
    const body = JSON.stringify(otlpJsonRequest()) + padding;
    const response = await handleRequest(request(body), env, { now: () => FIXED_NOW });
    expect(response.status).toBe(200);
  });

  it("refuses an unsupported content type with 415", async () => {
    const env = await envWithToken();
    const response = await handleRequest(
      request(JSON.stringify(otlpJsonRequest()), { "content-type": "text/plain" }),
      env,
    );
    expect(response.status).toBe(415);
  });

  it("refuses invalid JSON with 400 and does not echo the body", async () => {
    const env = await envWithToken();
    const response = await handleRequest(request('{"resourceSpans": 42, "secret":"nope"}'), env);
    expect(response.status).toBe(400);
    const body = await response.json();
    expect(body.error).toContain("invalid OTLP trace request");
    expect(JSON.stringify(body)).not.toContain("nope");
  });

  it("refuses a body that is not an OTLP envelope", async () => {
    const env = await envWithToken();
    const response = await handleRequest(request('"a string"'), env);
    expect(response.status).toBe(400);
  });

  it("counts malformed spans in partialSuccess instead of losing the batch", async () => {
    const env = await envWithToken();
    const body = otlpJsonRequest();
    const spans = (body as any).resourceSpans[0].scopeSpans[0].spans;
    spans.push({ traceId: "short", spanId: "b7ad6b7169203331", name: "bad" });

    const response = await handleRequest(request(JSON.stringify(body)), env, {
      now: () => FIXED_NOW,
    });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      partialSuccess: { rejectedSpans: 1, errorMessage: "spans rejected by digitrace-ingest" },
    });
    expect(env.__queue.sent[0].ndjson.trim().split("\n")).toHaveLength(1);
  });

  it("accepts an empty export without enqueueing anything", async () => {
    const env = await envWithToken();
    const response = await handleRequest(request(JSON.stringify({ resourceSpans: [] })), env);
    expect(response.status).toBe(200);
    expect(env.__queue.sent).toHaveLength(0);
  });

  it("enqueues nothing when sampling keeps no trace, and still answers 200", async () => {
    const env = await envWithToken();
    const response = await handleRequest(request(JSON.stringify(otlpJsonRequest())), env, {
      samplingRate: 0,
    });
    expect(response.status).toBe(200);
    expect(env.__queue.sent).toHaveLength(0);
  });
});

describe("POST /v1/traces, gzip", () => {
  it("inflates a gzip body and applies the cap to the inflated size", async () => {
    const env = await envWithToken();
    const body = new TextEncoder().encode(JSON.stringify(otlpJsonRequest()));
    const gzipped = new Uint8Array(
      await new Response(
        new Blob([body]).stream().pipeThrough(new CompressionStream("gzip")),
      ).arrayBuffer(),
    );

    const response = await handleRequest(request(gzipped, { "content-encoding": "gzip" }), env, {
      now: () => FIXED_NOW,
    });
    expect(response.status).toBe(200);
    expect(env.__queue.sent).toHaveLength(1);
  });

  it("refuses an encoding it cannot read", async () => {
    const env = await envWithToken();
    const response = await handleRequest(request("body", { "content-encoding": "br" }), env);
    expect(response.status).toBe(415);
  });
});

describe("POST /v1/traces, protobuf", () => {
  const TRACE_BYTES = [
    0x0a, 0xf7, 0x65, 0x19, 0x16, 0xcd, 0x43, 0xdd, 0x84, 0x48, 0xeb, 0x21, 0x1c, 0x80, 0x31, 0x9c,
  ];
  const SPAN_BYTES = [0xb7, 0xad, 0x6b, 0x71, 0x69, 0x20, 0x33, 0x31];

  function field(number: number, body: number[]): number[] {
    return [(number << 3) | 2, body.length, ...body];
  }

  function requestBytes(name: string): Uint8Array {
    const nameBytes = Array.from(new TextEncoder().encode(name));
    const span = [...field(1, TRACE_BYTES), ...field(2, SPAN_BYTES), ...field(5, nameBytes)];
    const scopeSpans = field(2, span);
    const resourceSpans = field(2, scopeSpans);
    return new Uint8Array(field(1, resourceSpans));
  }

  it("decodes a protobuf export and answers in protobuf", async () => {
    const env = await envWithToken();
    const response = await handleRequest(
      request(requestBytes("GET /pb"), { "content-type": "application/x-protobuf" }),
      env,
      { now: () => FIXED_NOW },
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/x-protobuf");
    expect((await response.arrayBuffer()).byteLength).toBe(0);

    const [message] = env.__queue.sent;
    const line = JSON.parse(message.ndjson.trim());
    expect(line.span.traceId).toBe("0af7651916cd43dd8448eb211c80319c");
    expect(line.span.spanId).toBe("b7ad6b7169203331");
    expect(line.span.name).toBe("GET /pb");
  });

  it("answers a corrupt protobuf body with 400 in the same encoding", async () => {
    const env = await envWithToken();
    const response = await handleRequest(
      request(new Uint8Array([0x0a, 0x40, 0x01]), { "content-type": "application/x-protobuf" }),
      env,
    );
    expect(response.status).toBe(400);
    expect(response.headers.get("content-type")).toBe("application/x-protobuf");
  });
});

describe("queue failure", () => {
  it("answers 503 so the source retries the request", async () => {
    const env = await envWithToken(undefined, { queueFail: true });
    const response = await handleRequest(request(JSON.stringify(otlpJsonRequest())), env, {
      now: () => FIXED_NOW,
    });
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      error: "ingest queue is unavailable, retry the request",
    });
  });
});

describe("chunking across queue messages", () => {
  it("splits a large request into ordered chunks that share a batch id", async () => {
    const env = await envWithToken();
    const body = otlpJsonRequest();
    const spans = (body as any).resourceSpans[0].scopeSpans[0].spans;
    for (let i = 0; i < 400; i += 1) {
      spans.push({
        ...spans[0],
        spanId: i.toString(16).padStart(16, "0"),
        name: `span-${i}`,
        attributes: [{ key: "blob", value: { stringValue: "x".repeat(600) } }],
      });
    }
    let uuid = 0;
    const response = await handleRequest(request(JSON.stringify(body)), env, {
      now: () => FIXED_NOW,
      newUuid: () => `uuid-${uuid++}`,
    });

    expect(response.status).toBe(200);
    expect(env.__queue.sent.length).toBeGreaterThan(1);
    const chunks = env.__queue.sent;
    expect(new Set(chunks.map((message) => message.batchId)).size).toBe(1);
    expect(chunks.map((message) => message.chunk)).toEqual(chunks.map((_, index) => index));
    expect(chunks.every((message) => message.chunks === chunks.length)).toBe(true);
    expect(new Set(chunks.map((message) => message.archiveKey)).size).toBe(chunks.length);
    for (const message of chunks) {
      expect(new TextEncoder().encode(message.ndjson).byteLength).toBeLessThanOrEqual(56 * 1024);
    }
  });
});

describe("routes", () => {
  it("answers the health probe", async () => {
    const env = await envWithToken();
    const response = await handleRequest(new Request("https://trace.digithings.ai/health"), env);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true, service: "digitrace-ingest" });
  });

  it("does not expose anything else", async () => {
    const env = await envWithToken();
    const response = await handleRequest(
      new Request("https://trace.digithings.ai/v1/logs", { method: "POST", body: "{}" }),
      env,
    );
    expect(response.status).toBe(404);
  });

  it("refuses a non-POST on the receiver with 405 and an Allow header", async () => {
    const env = await envWithToken();
    const response = await handleRequest(new Request(ENDPOINT, { method: "GET" }), env);
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("POST");
  });
});
