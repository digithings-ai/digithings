import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("_headers CSP", () => {
  it("allows digichat.digithings.ai iframe for /chat digigraph cutover", () => {
    const text = readFileSync(resolve(__dirname, "../public/_headers"), "utf8");
    expect(text).toMatch(/frame-src https:\/\/digichat\.digithings\.ai/);
    expect(text).not.toMatch(/frame-src 'none'/);
    expect(text).toMatch(/frame-ancestors 'none'/);
  });
});
