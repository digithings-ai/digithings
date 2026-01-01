import { afterEach, describe, expect, it, vi } from "vitest";
import { BoundedTTLMap } from "@/lib/bounded-map";

afterEach(() => {
  vi.useRealTimers();
});

describe("BoundedTTLMap", () => {
  it("returns undefined for a missing key", () => {
    const map = new BoundedTTLMap<string, number>(10, 60_000);
    expect(map.get("missing")).toBeUndefined();
  });

  it("expires entries after the default TTL", () => {
    vi.useFakeTimers();
    const map = new BoundedTTLMap<string, string>(10, 1_000);
    map.set("k", "v");
    expect(map.get("k")).toBe("v");
    vi.advanceTimersByTime(1_001);
    expect(map.get("k")).toBeUndefined();
  });

  it("honors a per-set TTL override shorter than the default", () => {
    vi.useFakeTimers();
    const map = new BoundedTTLMap<string, string>(10, 60_000);
    map.set("short", "v", 500);
    vi.advanceTimersByTime(501);
    expect(map.get("short")).toBeUndefined();
  });

  it("evicts the oldest key when capacity is exceeded", () => {
    const map = new BoundedTTLMap<string, number>(2, 60_000);
    map.set("a", 1);
    map.set("b", 2);
    map.set("c", 3);
    expect(map.get("a")).toBeUndefined();
    expect(map.get("b")).toBe(2);
    expect(map.get("c")).toBe(3);
  });

  it("updating an existing key does not count toward capacity eviction", () => {
    const map = new BoundedTTLMap<string, number>(2, 60_000);
    map.set("a", 1);
    map.set("b", 2);
    map.set("a", 11);
    expect(map.get("a")).toBe(11);
    expect(map.get("b")).toBe(2);
  });

  it("delete and clear remove entries", () => {
    const map = new BoundedTTLMap<string, number>(10, 60_000);
    map.set("a", 1);
    map.set("b", 2);
    map.delete("a");
    expect(map.get("a")).toBeUndefined();
    map.clear();
    expect(map.get("b")).toBeUndefined();
  });
});
