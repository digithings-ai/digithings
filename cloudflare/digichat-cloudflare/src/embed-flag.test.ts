/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { legacyEmbedEnabledValue } from "./embed-flag";

describe("legacyEmbedEnabledValue", () => {
  it("defaults the legacy anonymous embed OFF", () => {
    expect(legacyEmbedEnabledValue(undefined, undefined)).toBe("0");
    expect(legacyEmbedEnabledValue("", "")).toBe("0");
  });

  it("honors the documented DIGICHAT_LEGACY_EMBED_ENABLED opt-in", () => {
    expect(legacyEmbedEnabledValue("1", undefined)).toBe("1");
  });

  it("still honors the deprecated DIGICHAT_EMBED_ENABLED alias", () => {
    expect(legacyEmbedEnabledValue(undefined, "1")).toBe("1");
  });

  it("coerces anything other than 1 to off", () => {
    expect(legacyEmbedEnabledValue("0", "0")).toBe("0");
    expect(legacyEmbedEnabledValue("true", "yes")).toBe("0");
  });
});

describe("worker wiring", () => {
  const indexSrc = readFileSync(join(__dirname, "index.ts"), "utf8");

  it("forwards the documented legacy flag from the worker env", () => {
    expect(indexSrc).toMatch(/DIGICHAT_LEGACY_EMBED_ENABLED\?:/);
    expect(indexSrc).toMatch(/DIGICHAT_LEGACY_EMBED_ENABLED/);
    expect(indexSrc).toMatch(
      /DIGICHAT_EMBED_ENABLED:\s*legacyEmbedEnabledValue\(/,
    );
  });
});

describe("wrangler.toml production vars", () => {
  const wrangler = readFileSync(join(__dirname, "../wrangler.toml"), "utf8");

  it("does not enable the legacy anonymous embed by default", () => {
    expect(wrangler).not.toMatch(
      /^\s*DIGICHAT_(?:LEGACY_)?EMBED_ENABLED\s*=\s*"1"/m,
    );
  });
});

describe("self-host env templates", () => {
  const examples = [
    "../../../infra/digichat-release/.env.profile-a.example",
    "../../../infra/digichat-release/.env.profile-a-bundle.example",
    "../../../infra/digichat-release/.env.profile-b.example",
  ];

  for (const rel of examples) {
    it(`${rel} does not enable the legacy anonymous embed`, () => {
      const text = readFileSync(join(__dirname, rel), "utf8");
      expect(text).not.toMatch(
        /^\s*DIGICHAT_(?:LEGACY_)?EMBED_ENABLED\s*=\s*1\b/m,
      );
    });
  }
});
