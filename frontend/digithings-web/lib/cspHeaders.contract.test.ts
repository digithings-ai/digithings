import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("_headers CSP", () => {
  it("allows same-origin iframe via frame-src 'self'", () => {
    const text = readFileSync(resolve(__dirname, "../public/_headers"), "utf8");
    expect(text).toMatch(/Content-Security-Policy:/);
    expect(text).toMatch(/frame-src 'self'/);
    expect(text).not.toMatch(/chat\.digithings\.ai/);
  });
});
