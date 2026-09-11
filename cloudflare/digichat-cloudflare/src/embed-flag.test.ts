/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { legacyEmbedEnabledValue } from "./embed-flag";

describe("legacyEmbedEnabledValue", () => {
  it("defaults the legacy anonymous embed OFF", () => {
    expect(legacyEmbedEnabledValue(undefined)).toBe("0");
    expect(legacyEmbedEnabledValue("")).toBe("0");
  });

  it("preserves an explicit operator opt-in", () => {
    expect(legacyEmbedEnabledValue("1")).toBe("1");
  });
});

describe("wrangler.toml production vars", () => {
  const wrangler = readFileSync(join(__dirname, "../wrangler.toml"), "utf8");

  it("does not enable the legacy anonymous embed by default", () => {
    const match = wrangler.match(/^\s*DIGICHAT_EMBED_ENABLED\s*=\s*"([^"]*)"/m);
    expect(match?.[1] ?? "0").not.toBe("1");
  });
});
