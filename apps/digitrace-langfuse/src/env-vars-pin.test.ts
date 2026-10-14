/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Pins `langfuseEnvVars()` keys against the `Env` interface in index.ts —
 * same invariant as digichat-cloudflare / digithings-stack-cloudflare.
 * A secret `put` on the Worker but missing from langfuseEnvVars never reaches
 * either Container.
 */

const indexSource = readFileSync(join(__dirname, "index.ts"), "utf-8");

/** Env members that are bindings / Worker-only (not forwarded as container env). */
const WORKER_ONLY_ENV_MEMBERS: Record<string, string> = {
  LANGFUSE_WEB: "Durable Object binding",
  LANGFUSE_WORKER: "Durable Object binding",
  LANGFUSE_EVENTS: "R2 binding — Containers use S3 env, not this API",
};

function extractEnvInterfaceMembers(source: string): string[] {
  const match = source.match(/export interface Env \{([\s\S]*?)\n\}/);
  if (!match) {
    throw new Error("could not locate `export interface Env` in index.ts");
  }
  return [...match[1].matchAll(/^\s*([A-Z][A-Z0-9_]*)\??:/gm)].map((m) => m[1]);
}

function extractLangfuseEnvVarKeys(source: string): string[] {
  const match = source.match(
    /function langfuseEnvVars\(\)[\s\S]*?return \{([\s\S]*?)\n {2}\};/,
  );
  if (!match) {
    throw new Error("could not locate langfuseEnvVars() return block");
  }
  return [...match[1].matchAll(/^\s*([A-Z][A-Z0-9_]*)\s*:/gm)].map((m) => m[1]);
}

describe("langfuseEnvVars ↔ Env pin", () => {
  const envMembers = extractEnvInterfaceMembers(indexSource);
  const forwarded = extractLangfuseEnvVarKeys(indexSource);

  it("forwards every Env secret/var that is not Worker-only", () => {
    const expected = envMembers.filter((n) => !(n in WORKER_ONLY_ENV_MEMBERS));
    expect(expected.length).toBeGreaterThan(5);
    for (const name of expected) {
      expect(forwarded, `missing forward for ${name}`).toContain(name);
    }
  });

  it("does not forward Worker-only bindings", () => {
    for (const name of Object.keys(WORKER_ONLY_ENV_MEMBERS)) {
      expect(forwarded).not.toContain(name);
      expect(envMembers).toContain(name);
    }
  });

  it("every forwarded key is declared on Env", () => {
    for (const name of forwarded) {
      expect(envMembers, `forwarded ${name} not on Env`).toContain(name);
    }
  });
});
