/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
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

describe("license issuer forwarding", () => {
  const indexSource = readFileSync(join(__dirname, "index.ts"), "utf-8");
  const wranglerToml = readFileSync(join(__dirname, "..", "wrangler.toml"), "utf-8");

  it("forwards DIGIKEY_ISSUER into the container env with the prod default", () => {
    const envVars = indexSource.slice(indexSource.indexOf("envVars"));
    expect(envVars).toContain(
      'DIGIKEY_ISSUER: workerVars.DIGIKEY_ISSUER ?? "https://key.digithings.ai"',
    );
    expect(indexSource).toMatch(/\n\s+DIGIKEY_ISSUER\?: string;/);
  });

  it("sets the issuer under [vars] to match the stack", () => {
    const vars = wranglerToml.slice(wranglerToml.indexOf("\n[vars]"));
    expect(vars).toMatch(/^DIGIKEY_ISSUER = "https:\/\/key\.digithings\.ai"$/m);
  });
});
