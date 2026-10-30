import { describe, expect, it } from "vitest";
import { pemEnvValue } from "./license-env";

const PEM = "-----BEGIN PUBLIC KEY-----\nAAAA\nBBBB\n-----END PUBLIC KEY-----";

describe("pemEnvValue", () => {
  it("returns empty for unset or blank values", () => {
    expect(pemEnvValue(undefined)).toBe("");
    expect(pemEnvValue("  ")).toBe("");
  });

  it("keeps a PEM with real newlines as is", () => {
    expect(pemEnvValue(PEM)).toBe(PEM);
  });

  it("expands literal \\n sequences from a one-line secret", () => {
    expect(pemEnvValue(PEM.replace(/\n/g, "\\n"))).toBe(PEM);
  });
});
