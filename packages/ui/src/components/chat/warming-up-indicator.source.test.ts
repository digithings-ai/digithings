import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the warming-up indicator contract (#4753): while the digichat BFF
 * retries a booting upstream it replaces the `connecting` data-connection
 * part with `warming_up`, and the thread indicators must render warming copy
 * for that state — never the unavailable error, which stays reserved for
 * real (non-boot) failures.
 */
const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("warming-up indicator", () => {
  it("gallery thread renders warming copy for the warming_up connection state", () => {
    const thread = read("gallery-thread/thread.aui.tsx");
    expect(thread).toMatch(/warming_up/);
    expect(thread).toMatch(/Warming up…/);
    // Warming wins over connecting when both states are somehow present.
    const warmingIdx = thread.indexOf("warming_up");
    const connectingIdx = thread.indexOf("Connecting…");
    expect(warmingIdx).toBeGreaterThan(-1);
    expect(connectingIdx).toBeGreaterThan(-1);
    expect(warmingIdx).toBeLessThan(connectingIdx);
  });

  it("base skin swaps its empty-message copy while the upstream boots", () => {
    const thread = read("skins/base/thread.tsx");
    expect(thread).toMatch(/warming_up/);
    expect(thread).toMatch(/Warming up…/);
    // The plain "Connecting" copy stays for normal (non-boot) waits.
    expect(thread).toContain("Connecting");
  });
});
