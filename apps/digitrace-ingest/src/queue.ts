/**
 * Queue delivery.
 *
 * Cloudflare caps `sendBatch` at 100 messages and 256 KiB per call, and a single
 * request can produce more than that. The grouping below is by *bytes as well as
 * count*, because one message can already be ~120 KiB: grouping by count alone
 * would exceed the batch byte cap on the second message.
 */
import type { IngestMessage } from "./types";

/** The product's limits on one `sendBatch` call. */
export const MAX_BATCH_MESSAGES = 100;
export const MAX_BATCH_BYTES = 256 * 1024;
/** Headroom under the batch byte cap, for the envelope `sendBatch` adds. */
export const BATCH_BYTE_BUDGET = 200 * 1024;

const encoder = new TextEncoder();

/** The encoded size of one message body, as the queue would count it. */
export function messageBytes(message: IngestMessage): number {
  return encoder.encode(JSON.stringify(message)).length;
}

/** Group messages so no `sendBatch` call breaks a product limit. */
export function groupForSend(messages: IngestMessage[]): IngestMessage[][] {
  const groups: IngestMessage[][] = [];
  let current: IngestMessage[] = [];
  let bytes = 0;

  for (const message of messages) {
    const size = messageBytes(message);
    const full =
      current.length > 0 &&
      (current.length >= MAX_BATCH_MESSAGES || bytes + size > BATCH_BYTE_BUDGET);
    if (full) {
      groups.push(current);
      current = [];
      bytes = 0;
    }
    current.push(message);
    bytes += size;
  }
  if (current.length > 0) groups.push(current);
  return groups;
}

/** Enqueue every message, in as few `sendBatch` calls as the limits allow. */
export async function enqueue(
  queue: Queue<IngestMessage>,
  messages: IngestMessage[],
): Promise<void> {
  for (const group of groupForSend(messages)) {
    await queue.sendBatch(group.map((body) => ({ body })));
  }
}
