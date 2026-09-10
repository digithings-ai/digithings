import { afterEach, describe, expect, it } from "vitest";

import { getEnabledServiceIds, isServiceCapabilityEnabled } from "./capabilities";

describe("getEnabledServiceIds", () => {
  afterEach(() => {
    delete process.env.DIGICHAT_ENABLED_SERVICES;
  });

  it("falls back to all four services when the env var is unset", () => {
    delete process.env.DIGICHAT_ENABLED_SERVICES;
    expect(getEnabledServiceIds()).toEqual([
      "digigraph",
      "digisearch",
      "digiquant",
      "digismith",
    ]);
  });

  it("returns zero services when the env var is explicitly set to an empty string", () => {
    process.env.DIGICHAT_ENABLED_SERVICES = "";
    expect(getEnabledServiceIds()).toEqual([]);
  });

  it("returns zero services when the env var is whitespace only", () => {
    process.env.DIGICHAT_ENABLED_SERVICES = "   ";
    expect(getEnabledServiceIds()).toEqual([]);
  });

  it("parses an explicit comma-separated list", () => {
    process.env.DIGICHAT_ENABLED_SERVICES = "digigraph, digismith";
    expect(getEnabledServiceIds()).toEqual(["digigraph", "digismith"]);
  });
});

describe("isServiceCapabilityEnabled", () => {
  afterEach(() => {
    delete process.env.DIGICHAT_ENABLED_SERVICES;
  });

  it("is false for every service when the env var is explicitly empty", () => {
    process.env.DIGICHAT_ENABLED_SERVICES = "";
    expect(isServiceCapabilityEnabled("digigraph")).toBe(false);
    expect(isServiceCapabilityEnabled("digisearch")).toBe(false);
    expect(isServiceCapabilityEnabled("digiquant")).toBe(false);
    expect(isServiceCapabilityEnabled("digismith")).toBe(false);
  });
});
