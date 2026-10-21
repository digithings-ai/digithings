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

import { RESERVATION_TTL_MS, TOKEN_WINDOW_MS, type SpendEvent } from "./budget";

export type GuardrailSnapshot = {
  events: SpendEvent[];
  reserved: number;
};

export interface GuardrailStore {
  readonly kind: "memory" | "shared";
  read(key: string, now: number): GuardrailSnapshot;
  /** `at` is when the hold started. It expires after RESERVATION_TTL_MS. */
  reserve(key: string, reservationId: string, tokens: number, at: number): void;
  commit(key: string, reservationId: string, tokens: number, at: number): void;
  release(key: string, reservationId: string, at?: number): void;
}

type Hold = { tokens: number; at: number };

type Bucket = {
  events: SpendEvent[];
  reserved: Map<string, Hold>;
};

export class MemoryGuardrailStore implements GuardrailStore {
  readonly kind = "memory" as const;
  private readonly buckets = new Map<string, Bucket>();

  /** Live keys after expired spend and empty buckets have been dropped. */
  bucketCount(): number {
    return this.buckets.size;
  }

  read(key: string, now: number): GuardrailSnapshot {
    this.evict(now);
    const bucket = this.buckets.get(key);
    if (!bucket) return { events: [], reserved: 0 };
    let reserved = 0;
    for (const hold of bucket.reserved.values()) reserved += hold.tokens;
    return { events: bucket.events.map((event) => ({ ...event })), reserved };
  }

  reserve(key: string, reservationId: string, tokens: number, at: number): void {
    this.evict(at);
    if (tokens <= 0) return;
    this.bucket(key).reserved.set(reservationId, { tokens, at });
  }

  commit(key: string, reservationId: string, tokens: number, at: number): void {
    this.evict(at);
    const bucket = this.bucket(key);
    bucket.reserved.delete(reservationId);
    if (tokens > 0) bucket.events.push({ at, tokens });
    this.evict(at);
  }

  release(key: string, reservationId: string, at = Date.now()): void {
    this.buckets.get(key)?.reserved.delete(reservationId);
    this.evict(at);
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

  private evict(now: number): void {
    const eventCutoff = now - TOKEN_WINDOW_MS;
    const holdCutoff = now - RESERVATION_TTL_MS;
    for (const [key, bucket] of this.buckets) {
      bucket.events = bucket.events.filter((event) => event.at > eventCutoff);
      for (const [id, hold] of bucket.reserved) {
        if (hold.at <= holdCutoff) bucket.reserved.delete(id);
      }
      if (bucket.events.length === 0 && bucket.reserved.size === 0) {
        this.buckets.delete(key);
      }
    }
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
