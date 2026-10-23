/**
 * Process-local counters for limits. Same constraint as the token-window
 * store: one Node instance. A shared store can replace it later; this module
 * does not create a Cloudflare namespace or a Durable Object.
 */

import type { LimitWindow } from "./schema";

export type Price = { inputPerM: number; outputPerM: number };

export type Usage = {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
};

type Lease = { id: string; at: number };
type Spend = { at: number; amount: number };

export class LimitsMemory {
  private readonly events = new Map<string, Spend[]>();
  private readonly leases = new Map<string, Lease[]>();

  /** `windowMs` null keeps every event on the key (a session window). */
  add(key: string, amount: number, at: number): void {
    if (!(amount > 0)) return;
    const kept = this.liveEvents(key, at, null);
    kept.push({ at, amount });
    this.events.set(key, kept);
  }

  read(key: string, at: number, windowMs: number | null): number {
    const kept = this.liveEvents(key, at, windowMs);
    let total = 0;
    for (const event of kept) total += event.amount;
    return total;
  }

  noteSession(key: string, id: string, at: number): void {
    const list = this.liveLeases(key, at, null, null);
    const existing = list.find((lease) => lease.id === id);
    if (existing) existing.at = at;
    else list.push({ id, at });
    this.leases.set(key, list);
  }

  sessionCount(key: string, at: number, idleMs: number | null, windowStart: number | null): number {
    return this.liveLeases(key, at, idleMs, windowStart).length;
  }

  hasSession(
    key: string,
    id: string,
    at: number,
    idleMs: number | null,
    windowStart: number | null,
  ): boolean {
    return this.liveLeases(key, at, idleMs, windowStart).some((lease) => lease.id === id);
  }

  clear(): void {
    this.events.clear();
    this.leases.clear();
  }

  private liveEvents(key: string, at: number, windowMs: number | null): Spend[] {
    const list = this.events.get(key) ?? [];
    const kept =
      windowMs == null ? list : list.filter((event) => at - event.at < windowMs && event.at <= at);
    if (kept.length !== list.length) {
      if (kept.length) this.events.set(key, kept);
      else this.events.delete(key);
    }
    return kept;
  }

  private liveLeases(
    key: string,
    at: number,
    idleMs: number | null,
    windowStart: number | null,
  ): Lease[] {
    const list = this.leases.get(key) ?? [];
    const kept = list.filter((lease) => {
      if (lease.at > at) return false;
      if (idleMs != null && at - lease.at > idleMs) return false;
      if (windowStart != null && lease.at < windowStart) return false;
      return true;
    });
    if (kept.length !== list.length) {
      if (kept.length) this.leases.set(key, kept);
      else this.leases.delete(key);
    }
    return kept;
  }
}

const SHARED = Symbol.for("digichat.limitsStore");
const processStore = new LimitsMemory();

type GlobalStore = typeof globalThis & { [SHARED]?: LimitsMemory };

export function activeLimitsStore(): LimitsMemory {
  return (globalThis as GlobalStore)[SHARED] ?? processStore;
}

export function installLimitsStore(store: LimitsMemory | undefined): void {
  const g = globalThis as GlobalStore;
  if (store) g[SHARED] = store;
  else delete g[SHARED];
}

export function resetLimitsStoreForTests(): void {
  processStore.clear();
  installLimitsStore(undefined);
}

/** Rolling windows. A day is 86400 seconds, not a calendar date. */
export function windowDurationMs(window: LimitWindow): number | null {
  if (window === "minute") return 60_000;
  if (window === "hour") return 3_600_000;
  if (window === "day") return 86_400_000;
  return null;
}

export function bucketFor(window: LimitWindow, sessionId: string): string {
  if (window === "session") return `s:${sessionId}`;
  return window;
}

export function windowStart(window: LimitWindow, at: number): number | null {
  const duration = windowDurationMs(window);
  return duration == null ? null : at - duration;
}

export function usdForTokens(usage: Usage, price: Price): number {
  const input = finite(usage.inputTokens) ?? 0;
  const output = finite(usage.outputTokens) ?? 0;
  if (input === 0 && output === 0) {
    const total = finite(usage.totalTokens) ?? 0;
    if (total <= 0) return 0;
    return (total / 1_000_000) * Math.max(price.inputPerM, price.outputPerM);
  }
  return (input / 1_000_000) * price.inputPerM + (output / 1_000_000) * price.outputPerM;
}

function finite(value: number | undefined): number | undefined {
  return value != null && Number.isFinite(value) && value > 0 ? value : undefined;
}
