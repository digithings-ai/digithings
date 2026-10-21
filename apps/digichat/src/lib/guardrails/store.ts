/**
 * Rolling token window storage.
 *
 * The default store is process-local: one Node instance, one window. The
 * digichat container does not hold the Cloudflare Worker's KV namespace or a
 * Durable Object binding (those stay on the worker, which only forwards tenant
 * JSON). `installGuardrailStore` is the seam a host with that shared storage
 * would fill. Nothing in this repo installs one, and this change does not
 * create a namespace or a Durable Object.
 */

import { TOKEN_WINDOW_MS, type SpendEvent } from "./budget";

export type GuardrailSnapshot = {
  events: SpendEvent[];
  reserved: number;
};

export interface GuardrailStore {
  readonly kind: "memory" | "shared";
  read(key: string, now: number): GuardrailSnapshot;
  reserve(key: string, reservationId: string, tokens: number): void;
  commit(key: string, reservationId: string, tokens: number, at: number): void;
  release(key: string, reservationId: string): void;
}

type Bucket = {
  events: SpendEvent[];
  reserved: Map<string, number>;
};

export class MemoryGuardrailStore implements GuardrailStore {
  readonly kind = "memory" as const;
  private readonly buckets = new Map<string, Bucket>();

  read(key: string, now: number): GuardrailSnapshot {
    const bucket = this.buckets.get(key);
    if (!bucket) return { events: [], reserved: 0 };
    this.prune(bucket, now);
    let reserved = 0;
    for (const tokens of bucket.reserved.values()) reserved += tokens;
    return { events: bucket.events.map((event) => ({ ...event })), reserved };
  }

  reserve(key: string, reservationId: string, tokens: number): void {
    if (tokens <= 0) return;
    this.bucket(key).reserved.set(reservationId, tokens);
  }

  commit(key: string, reservationId: string, tokens: number, at: number): void {
    const bucket = this.bucket(key);
    bucket.reserved.delete(reservationId);
    if (tokens > 0) bucket.events.push({ at, tokens });
    this.prune(bucket, at);
  }

  release(key: string, reservationId: string): void {
    this.buckets.get(key)?.reserved.delete(reservationId);
  }

  clear(): void {
    this.buckets.clear();
  }

  private bucket(key: string): Bucket {
    let bucket = this.buckets.get(key);
    if (!bucket) {
      bucket = { events: [], reserved: new Map() };
      this.buckets.set(key, bucket);
    }
    return bucket;
  }

  private prune(bucket: Bucket, now: number): void {
    const cutoff = now - TOKEN_WINDOW_MS;
    bucket.events = bucket.events.filter((event) => event.at > cutoff);
  }
}

const SHARED = Symbol.for("digichat.guardrailStore");
const processStore = new MemoryGuardrailStore();

type GlobalGuard = typeof globalThis & { [SHARED]?: GuardrailStore };

/** The store this process uses. A shared store, when installed, wins. */
export function activeGuardrailStore(): GuardrailStore {
  return (globalThis as GlobalGuard)[SHARED] ?? processStore;
}

/**
 * Install a store backed by shared storage, or pass undefined to go back to
 * the per-instance window. Tests use this; production does not.
 */
export function installGuardrailStore(store: GuardrailStore | undefined): void {
  const g = globalThis as GlobalGuard;
  if (store) g[SHARED] = store;
  else delete g[SHARED];
}

export function resetGuardrailStoreForTests(): void {
  processStore.clear();
  installGuardrailStore(undefined);
}
