/** In-memory map with max entry count and per-entry TTL eviction. */

type Entry<V> = { value: V; expiresAtMs: number };

export class BoundedTTLMap<K, V> {
  private readonly map = new Map<K, Entry<V>>();

  constructor(
    private readonly maxEntries: number,
    private readonly ttlMs: number
  ) {}

  get(key: K): V | undefined {
    this.evictExpired();
    const hit = this.map.get(key);
    if (!hit) return undefined;
    if (hit.expiresAtMs <= Date.now()) {
      this.map.delete(key);
      return undefined;
    }
    return hit.value;
  }

  set(key: K, value: V, ttlMs: number = this.ttlMs): void {
    this.evictExpired();
    if (!this.map.has(key) && this.map.size >= this.maxEntries) {
      const oldest = this.map.keys().next().value;
      if (oldest !== undefined) this.map.delete(oldest);
    }
    this.map.set(key, { value, expiresAtMs: Date.now() + ttlMs });
  }

  delete(key: K): void {
    this.map.delete(key);
  }

  clear(): void {
    this.map.clear();
  }

  private evictExpired(): void {
    const now = Date.now();
    for (const [key, entry] of this.map) {
      if (entry.expiresAtMs <= now) this.map.delete(key);
    }
  }
}
