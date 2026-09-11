/**
 * Full-app slash remainder-force is armed on prefs sessionKey (`app:anon`),
 * not the AI SDK chat `id` (#3741 review).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const src = readFileSync(join(__dirname, "home-stock-client.tsx"), "utf8");

describe("HomeStockClient force-tool key", () => {
  it("takes pending force-tool and web-search from sessionKey, not chat id", () => {
    expect(src).toMatch(/takePendingForceTool\(sessionKey\)/);
    expect(src).toMatch(/takePendingWebSearchForce\(sessionKey\)/);
    expect(src).toMatch(/X-Digi-Mcp-Session/);
    expect(src).toMatch(/X-Digi-Effort/);
    expect(src).not.toMatch(/takePendingForceTool\(threadKey\)/);
    expect(src).not.toMatch(/takePendingWebSearchForce\(threadKey\)/);
  });
});
