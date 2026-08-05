import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("_headers CSP", () => {
  it("does not allow framing (native /chat, no DigiChat iframe)", () => {
    const text = readFileSync(resolve(__dirname, "../public/_headers"), "utf8");
    expect(text).toMatch(/frame-src 'none'/);
    expect(text).not.toMatch(/frame-src 'self'/);
  });
});
