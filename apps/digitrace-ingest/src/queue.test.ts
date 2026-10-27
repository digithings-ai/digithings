import { describe, expect, it } from "vitest";
import {
  BATCH_BYTE_BUDGET,
  MAX_BATCH_MESSAGES,
  enqueue,
  groupForSend,
  messageBytes,
} from "./queue";
import { fakeQueue } from "../test/fakes";
import type { IngestMessage } from "./types";

function message(index: number, ndjsonBytes = 100): IngestMessage {
  return {
    v: 1,
    batchId: "batch",
    chunk: index,
    chunks: 1,
    tenant: "digithings",
    tenantSlugVerified: false,
    source: "digitrace-digichat",
    receivedAt: "2026-10-26T12:00:00.000Z",
    archiveKey: `tenant=digithings/date=2026-10-26/digitrace-digichat/${index}.ndjson`,
    ndjson: `${"x".repeat(ndjsonBytes)}\n`,
  };
}

describe("groupForSend", () => {
  it("keeps everything in one group when it fits", () => {
    expect(groupForSend([message(0), message(1)])).toHaveLength(1);
  });

  it("never exceeds the message count per call", () => {
    const messages = Array.from({ length: MAX_BATCH_MESSAGES * 2 + 5 }, (_, index) =>
      message(index),
    );
    const groups = groupForSend(messages);
    expect(groups.every((group) => group.length <= MAX_BATCH_MESSAGES)).toBe(true);
    expect(groups.flat()).toHaveLength(messages.length);
    expect(groups).toHaveLength(3);
  });

  it("never exceeds the byte budget, even when every message is large", () => {
    // A message near the queue ceiling: two of these cannot share a call.
    const messages = Array.from({ length: 4 }, (_, index) => message(index, 110 * 1024));
    const one = messageBytes(messages[0]);
    expect(one).toBeGreaterThan(BATCH_BYTE_BUDGET / 2);

    const groups = groupForSend(messages);
    expect(groups).toHaveLength(4);
    for (const group of groups) {
      const bytes = group.reduce((total, item) => total + messageBytes(item), 0);
      expect(bytes).toBeLessThanOrEqual(BATCH_BYTE_BUDGET);
    }
  });

  it("returns no groups for no messages", () => {
    expect(groupForSend([])).toEqual([]);
  });
});

describe("enqueue", () => {
  it("sends every message exactly once, across the batches it needs", async () => {
    const queue = fakeQueue();
    const messages = Array.from({ length: MAX_BATCH_MESSAGES + 1 }, (_, index) => message(index));
    await enqueue(queue.queue, messages);

    expect(queue.sent).toHaveLength(messages.length);
    expect(queue.calls).toEqual([MAX_BATCH_MESSAGES, 1]);
    expect(queue.sent.map((sent) => sent.archiveKey)).toEqual(
      messages.map((sent) => sent.archiveKey),
    );
  });

  it("propagates a queue failure so the receiver can answer 503", async () => {
    const queue = fakeQueue({ fail: true });
    await expect(enqueue(queue.queue, [message(0)])).rejects.toThrow("queue unavailable");
  });
});
