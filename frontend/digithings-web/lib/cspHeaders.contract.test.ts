import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("_headers CSP", () => {
  it("allows digichat origin in frame-src", () => {
    const text = readFileSync(resolve(__dirname, "../public/_headers"), "utf8");
    expect(text).toMatch(/Content-Security-Policy:/);
    expect(text).toMatch(/frame-src[^;]*https:\/\/chat\.digithings\.ai/);
  });
});
