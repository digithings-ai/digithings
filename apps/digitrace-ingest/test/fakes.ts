/**
 * Test doubles for the Worker's bindings.
 *
 * These are fakes, not emulators: each one records what the Worker asked it to
 * do, so a test can assert the contract (key layout, upsert target, metric
 * point) without a Miniflare runtime. They are deliberately outside `src/` so
 * `tsc --noEmit` treats the Worker program as the thing under test.
 */
import type { Env, IngestMessage } from "../src/types";

export interface SentBatch {
  body: IngestMessage;
}

export interface FakeQueue {
  queue: Queue<IngestMessage>;
  /** Every message sent, in order, across all `sendBatch` calls. */
  sent: IngestMessage[];
  /** Sizes of each `sendBatch` call, so a batching test can see the grouping. */
  calls: number[];
}

export function fakeQueue(options: { fail?: boolean } = {}): FakeQueue {
  const sent: IngestMessage[] = [];
  const calls: number[] = [];
  const queue = {
    async sendBatch(messages: SentBatch[]) {
      if (options.fail) throw new Error("queue unavailable");
      calls.push(messages.length);
      for (const message of messages) sent.push(message.body);
      return { metadata: { metrics: { backlogCount: 0, backlogBytes: 0 } } };
    },
    async send(message: SentBatch) {
      if (options.fail) throw new Error("queue unavailable");
      sent.push(message.body);
      return { metadata: { metrics: { backlogCount: 0, backlogBytes: 0 } } };
    },
  } as unknown as Queue<IngestMessage>;
  return { queue, sent, calls };
}

export interface StoredObject {
  key: string;
  body: string;
  options: R2PutOptions | undefined;
}

export interface FakeArchive {
  bucket: R2Bucket;
  objects: Map<string, StoredObject>;
  fail: boolean;
}

export function fakeArchive(options: { fail?: boolean } = {}): FakeArchive {
  const objects = new Map<string, StoredObject>();
  const state: FakeArchive = { objects, fail: options.fail === true } as FakeArchive;
  state.bucket = {
    async put(key: string, body: string, putOptions?: R2PutOptions) {
      if (state.fail) throw new Error("r2 unavailable");
      objects.set(key, { key, body, options: putOptions });
      return null;
    },
  } as unknown as R2Bucket;
  return state;
}

export interface FakeKv {
  namespace: KVNamespace;
  reads: string[];
}

export function fakeKv(entries: Record<string, string>): FakeKv {
  const reads: string[] = [];
  const namespace = {
    async get(key: string) {
      reads.push(key);
      return entries[key] ?? null;
    },
  } as unknown as KVNamespace;
  return { namespace, reads };
}

export interface FakeAnalytics {
  dataset: AnalyticsEngineDataset;
  points: AnalyticsEngineDataPoint[];
}

export function fakeAnalytics(): FakeAnalytics {
  const points: AnalyticsEngineDataPoint[] = [];
  const dataset = {
    writeDataPoint(point: AnalyticsEngineDataPoint) {
      points.push(point);
    },
  } as AnalyticsEngineDataset;
  return { dataset, points };
}

export interface TestEnv extends Env {
  __queue: FakeQueue;
  __archive: FakeArchive;
  __kv: FakeKv;
  __analytics: FakeAnalytics;
}

export function testEnv(
  options: {
    tokens?: Record<string, string>;
    queueFail?: boolean;
    archiveFail?: boolean;
    indexDb?: D1Database;
  } = {},
): TestEnv {
  const queue = fakeQueue({ fail: options.queueFail });
  const archive = fakeArchive({ fail: options.archiveFail });
  const kv = fakeKv(options.tokens ?? {});
  const analytics = fakeAnalytics();
  return {
    ARCHIVE: archive.bucket,
    INGEST_TOKENS: kv.namespace,
    INGEST_QUEUE: queue.queue,
    ANALYTICS: analytics.dataset,
    INDEX_DB: options.indexDb,
    __queue: queue,
    __archive: archive,
    __kv: kv,
    __analytics: analytics,
  };
}

/** A minimal, valid OTLP/JSON trace export request. */
export function otlpJsonRequest(
  overrides: {
    traceId?: string;
    spanId?: string;
    parentSpanId?: string;
    name?: string;
    startUnixNano?: string;
    endUnixNano?: string;
    kind?: number;
    attributes?: Array<{ key: string; value: unknown }>;
    resourceAttributes?: Array<{ key: string; value: unknown }>;
  } = {},
): Record<string, unknown> {
  return {
    resourceSpans: [
      {
        resource: {
          attributes: overrides.resourceAttributes ?? [
            { key: "service.name", value: { stringValue: "digitrace-test" } },
          ],
        },
        scopeSpans: [
          {
            scope: { name: "digitrace.test", version: "1.0.0" },
            spans: [
              {
                traceId: overrides.traceId ?? "0af7651916cd43dd8448eb211c80319c",
                spanId: overrides.spanId ?? "b7ad6b7169203331",
                parentSpanId: overrides.parentSpanId,
                name: overrides.name ?? "GET /chat",
                kind: overrides.kind ?? 2,
                startTimeUnixNano: overrides.startUnixNano ?? "1700000000000000000",
                endTimeUnixNano: overrides.endUnixNano ?? "1700000000120000000",
                attributes: overrides.attributes ?? [],
              },
            ],
          },
        ],
      },
    ],
  };
}
