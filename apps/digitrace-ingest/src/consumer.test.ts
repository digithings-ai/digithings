import { describe, expect, it, vi } from "vitest";
import {
  BASE_RETRY_DELAY_SECONDS,
  MAX_RETRY_DELAY_SECONDS,
  handleQueue,
  parseMessage,
  recordsFromNdjson,
  retryDelaySeconds,
  storeMessage,
  type ConsumerDeps,
} from "./consumer";
import { testEnv, type TestEnv } from "../test/fakes";
import type { IngestMessage } from "./types";

const TRACE = "0af7651916cd43dd8448eb211c80319c";
const SPAN = "b7ad6b7169203331";
const WORKSPACE = "11111111-2222-3333-4444-555555555555";
const RECEIVED = "2026-10-26T12:00:00.000Z";

function message(overrides: Partial<IngestMessage> = {}): IngestMessage {
  const line = {
    tenant_slug: "digithings",
    tenant_slug_verified: false,
    source: "digitrace-digichat",
    batch_id: "batch-1",
    chunk: 0,
    chunks: 1,
    received_at: RECEIVED,
    resource: { attributes: [{ key: "service.name", value: { stringValue: "digichat" } }] },
    scope: { name: "scope.a" },
    span: {
      traceId: TRACE,
      spanId: SPAN,
      name: "GET /chat",
      kind: 2,
      startTimeUnixNano: "1700000000000000000",
      endTimeUnixNano: "1700000000120000000",
      attributes: [],
    },
  };
  return {
    v: 1,
    batchId: "batch-1",
    chunk: 0,
    chunks: 1,
    tenant: "digithings",
    tenantSlugVerified: false,
    source: "digitrace-digichat",
    receivedAt: RECEIVED,
    archiveKey: "tenant=digithings/date=2026-10-26/digitrace-digichat/uuid-1.ndjson",
    ndjson: `${JSON.stringify(line)}\n`,
    ...overrides,
  };
}

interface FakeBatch {
  batch: MessageBatch<IngestMessage>;
  retries: Array<{ id: string; options: { delaySeconds?: number } | undefined }>;
  acks: string[];
}

function fakeBatch(entries: Array<{ id: string; body: unknown; attempts?: number }>): FakeBatch {
  const retries: FakeBatch["retries"] = [];
  const acks: string[] = [];
  const messages = entries.map((entry) => ({
    id: entry.id,
    timestamp: new Date(RECEIVED),
    body: entry.body,
    attempts: entry.attempts ?? 1,
    retry(options?: { delaySeconds?: number }) {
      retries.push({ id: entry.id, options });
    },
    ack() {
      acks.push(entry.id);
    },
  }));
  return {
    batch: { queue: "digitrace-ingest", messages } as unknown as MessageBatch<IngestMessage>,
    retries,
    acks,
  };
}

interface Recorded {
  puts: Array<{ key: string; body: string; metadata: Record<string, string> }>;
  upserts: Array<{ table: string; rows: Array<Record<string, unknown>>; onConflict: string }>;
  metrics: number;
  resolved: string[];
}

function recordingDeps(overrides: Partial<ConsumerDeps> = {}): {
  deps: Partial<ConsumerDeps>;
  recorded: Recorded;
} {
  const recorded: Recorded = { puts: [], upserts: [], metrics: 0, resolved: [] };
  const deps: Partial<ConsumerDeps> = {
    putObject: async (_bucket, key, body, metadata) => {
      recorded.puts.push({ key, body, metadata });
    },
    resolveWorkspaceId: async (_env, slug) => {
      recorded.resolved.push(slug);
      return WORKSPACE;
    },
    upsertRows: async (_env, table, rows, onConflict) => {
      recorded.upserts.push({ table, rows, onConflict });
    },
    writeSpanMetric: () => {
      recorded.metrics += 1;
    },
    ...overrides,
  };
  return { deps, recorded };
}

describe("parseMessage", () => {
  it("accepts a message the receiver produced", () => {
    expect(parseMessage(message())).toEqual(message());
  });

  it("rejects a message whose key is not under its own tenant", () => {
    expect(
      parseMessage(message({ archiveKey: "tenant=someone-else/date=2026-10-26/s/u.ndjson" })),
    ).toBeUndefined();
  });

  it("rejects an unknown version, a bad slug, or missing fields", () => {
    expect(parseMessage({ ...message(), v: 2 })).toBeUndefined();
    expect(parseMessage(message({ tenant: "Not A Slug" }))).toBeUndefined();
    expect(parseMessage(message({ ndjson: "" }))).toBeUndefined();
    expect(parseMessage(message({ source: "" }))).toBeUndefined();
    expect(parseMessage(null)).toBeUndefined();
    expect(parseMessage("body")).toBeUndefined();
  });

  it("never trusts a truthy non-boolean for tenant_slug_verified", () => {
    const parsed = parseMessage({ ...message(), tenantSlugVerified: "yes" });
    expect(parsed?.tenantSlugVerified).toBe(false);
  });
});

describe("recordsFromNdjson", () => {
  it("reads one record per line and skips a broken line", () => {
    const good = message().ndjson.trim();
    const records = recordsFromNdjson(`${good}\nnot json\n\n${good}\n`);
    expect(records).toHaveLength(2);
    expect(records[0].span.spanId).toBe(SPAN);
  });

  it("skips a line without a usable span", () => {
    expect(recordsFromNdjson('{"resource":{}}\n')).toEqual([]);
  });
});

describe("storeMessage", () => {
  it("writes the archive object first, with the tenant edges as metadata", async () => {
    const env = testEnv();
    const { deps, recorded } = recordingDeps();
    await storeMessage(env, message(), { ...deps } as ConsumerDeps);

    expect(recorded.puts).toHaveLength(1);
    expect(recorded.puts[0]).toMatchObject({
      key: "tenant=digithings/date=2026-10-26/digitrace-digichat/uuid-1.ndjson",
      metadata: {
        tenant: "digithings",
        tenant_slug_verified: "false",
        source: "digitrace-digichat",
        batch_id: "batch-1",
        chunk: "0/1",
      },
    });
  });

  it("resolves the workspace from the verified tenant slug", async () => {
    const { deps, recorded } = recordingDeps();
    await storeMessage(testEnv(), message(), { ...deps } as ConsumerDeps);
    expect(recorded.resolved).toEqual(["digithings"]);
  });

  it("upserts traces, spans and sessions with the natural key of each table", async () => {
    const { deps, recorded } = recordingDeps();
    await storeMessage(testEnv(), message(), { ...deps } as ConsumerDeps);

    expect(recorded.upserts.map((entry) => entry.table)).toEqual([
      "digitrace_traces",
      "digitrace_spans_index",
      "digitrace_sessions",
    ]);
    expect(recorded.upserts.map((entry) => entry.onConflict)).toEqual([
      "workspace_id,trace_id",
      "workspace_id,trace_id,span_id",
      "workspace_id,session_id",
    ]);
    expect(recorded.upserts[0].rows[0]).toMatchObject({
      workspace_id: WORKSPACE,
      trace_id: TRACE,
      received_at: RECEIVED,
    });
    expect(recorded.upserts[1].rows[0]).toMatchObject({ span_id: SPAN });
    // No session id attribute on this span, so no session row is sent.
    expect(recorded.upserts[2].rows).toEqual([]);
  });

  it("writes one metric point per span", async () => {
    const { deps, recorded } = recordingDeps();
    await storeMessage(testEnv(), message(), { ...deps } as ConsumerDeps);
    expect(recorded.metrics).toBe(1);
  });
});

describe("handleQueue", () => {
  it("acknowledges a message it stored, without retrying", async () => {
    const { deps, recorded } = recordingDeps();
    const { batch, retries } = fakeBatch([{ id: "m1", body: message() }]);
    await handleQueue(batch, testEnv(), deps);

    expect(recorded.puts).toHaveLength(1);
    expect(retries).toEqual([]);
  });

  it("retries when the archive write fails", async () => {
    const { deps } = recordingDeps({
      putObject: async () => {
        throw new Error("r2 unavailable");
      },
    });
    const { batch, retries } = fakeBatch([{ id: "m1", body: message(), attempts: 2 }]);
    await handleQueue(batch, testEnv(), deps);

    expect(retries).toEqual([{ id: "m1", options: { delaySeconds: retryDelaySeconds(2) } }]);
  });

  it("retries when the index write fails, after the archive is already stored", async () => {
    const { deps, recorded } = recordingDeps({
      upsertRows: async () => {
        throw new Error("PostgREST 500: explosion");
      },
    });
    const { batch, retries } = fakeBatch([{ id: "m1", body: message() }]);
    await handleQueue(batch, testEnv(), deps);

    expect(recorded.puts).toHaveLength(1);
    expect(retries).toHaveLength(1);
  });

  it("retries when Supabase is not configured, rather than skipping the index silently", async () => {
    const env = testEnv({ supabaseKey: "" });
    // Only the archive is stubbed: the real `resolveWorkspaceId` runs, and it is
    // the missing secret that must surface as a retry.
    const { deps } = recordingDeps();
    const { resolveWorkspaceId: _omit, ...rest } = deps;
    const { batch, retries } = fakeBatch([{ id: "m1", body: message() }]);
    await handleQueue(batch, env, rest);

    expect(retries).toHaveLength(1);
    expect(retries[0].options?.delaySeconds).toBe(retryDelaySeconds(1));
  });

  it("acknowledges a malformed message instead of retrying it for ever", async () => {
    const { deps, recorded } = recordingDeps();
    const { batch, retries, acks } = fakeBatch([{ id: "bad", body: { v: 99 } }]);
    await handleQueue(batch, testEnv(), deps);

    expect(recorded.puts).toHaveLength(0);
    expect(retries).toEqual([]);
    expect(acks).toEqual(["bad"]);
  });

  it("handles each message of a batch on its own", async () => {
    let calls = 0;
    const { deps } = recordingDeps({
      putObject: async () => {
        calls += 1;
        if (calls === 2) throw new Error("r2 unavailable");
      },
    });
    const { batch, retries } = fakeBatch([
      { id: "good", body: message() },
      { id: "bad", body: message({ archiveKey: "tenant=digithings/date=2026-10-26/x/2.ndjson" }) },
      {
        id: "good-2",
        body: message({ archiveKey: "tenant=digithings/date=2026-10-26/x/3.ndjson" }),
      },
    ]);
    await handleQueue(batch, testEnv(), deps);

    expect(retries).toHaveLength(1);
    expect(retries[0].id).toBe("bad");
  });

  it("does not throw out of the handler, so the rest of the batch survives", async () => {
    const { deps } = recordingDeps({
      putObject: async () => {
        throw new Error("r2 unavailable");
      },
    });
    const { batch } = fakeBatch([{ id: "m1", body: message() }]);
    await expect(handleQueue(batch, testEnv(), deps)).resolves.toBeUndefined();
  });

  it("logs a retry without the message body", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { deps } = recordingDeps({
      putObject: async () => {
        throw new Error("r2 unavailable");
      },
    });
    const { batch } = fakeBatch([{ id: "m1", body: message() }]);
    await handleQueue(batch, testEnv(), deps);

    const logged = JSON.stringify(warn.mock.calls);
    expect(logged).toContain("m1");
    expect(logged).not.toContain(SPAN);
    expect(logged).not.toContain(TRACE);
    warn.mockRestore();
  });
});

describe("retryDelaySeconds", () => {
  it("starts at the base delay and grows", () => {
    expect(retryDelaySeconds(1)).toBe(BASE_RETRY_DELAY_SECONDS);
    expect(retryDelaySeconds(2)).toBe(BASE_RETRY_DELAY_SECONDS * 2);
    expect(retryDelaySeconds(3)).toBe(BASE_RETRY_DELAY_SECONDS * 4);
  });

  it("never exceeds the maximum, and never returns a negative delay", () => {
    expect(retryDelaySeconds(20)).toBe(MAX_RETRY_DELAY_SECONDS);
    expect(retryDelaySeconds(0)).toBeGreaterThan(0);
  });
});

describe("a retried message is idempotent", () => {
  it("writes the same archive key and the same rows on every attempt", async () => {
    const first = recordingDeps();
    const second = recordingDeps();
    await storeMessage(testEnv(), message(), { ...first.deps } as ConsumerDeps);
    await storeMessage(testEnv(), message(), { ...second.deps } as ConsumerDeps);

    expect(first.recorded.puts).toEqual(second.recorded.puts);
    expect(first.recorded.upserts).toEqual(second.recorded.upserts);
  });
});
