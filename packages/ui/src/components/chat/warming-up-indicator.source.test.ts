import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the warming-up indicator contract (#4753): while the digichat BFF
 * retries a booting upstream it replaces the `connecting` data-connection
 * part with `warming_up` and sends the line to show with it; the thread
 * indicators render that message — never the unavailable error, which stays
 * reserved for real (non-boot) failures — and never a copy of their own.
 */
const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("warming-up indicator", () => {
  it("both skins read the server's status message, with no fallback copy", () => {
    for (const rel of ["gallery-thread/thread.aui.tsx", "skins/base/thread.tsx"]) {
      const thread = read(rel);
      expect(thread).toMatch(/connectionStatusText/);
      // DIG-4459: no client-side default line for any connection state.
      expect(thread).not.toMatch(/Warming up…/);
      expect(thread).not.toMatch(/Connecting…|"Connecting"|\?\? "Connecting"/);
    }
  });

  it("the BFF names the boot wait itself", () => {
    const stream = read("../../../../../apps/digichat/src/lib/adapters/digithings/stream.ts");
    expect(stream).toMatch(/state: "warming_up", message: "Waking up services…"/);
  });
});
