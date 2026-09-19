/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Pins `DigiChatContainer.envVars` (the object forwarded into the Container's
 * runtime env) against the `Env` interface (the Worker's typed binding surface)
 * in index.ts -- same invariant as digithings-stack-cloudflare's
 * src/env-vars-pin.test.js (issues #2239 / #4314).
 *
 * A var declared on `Env` but missing from `envVars` typechecks cleanly and
 * silently never reaches the running digichat process. tsc catches only the
 * opposite direction (an `env`/`workerVars` read not on `Env` is
 * `Property 'X' does not exist on type 'Env'`); an unused interface member is not
 * an error. This file closes the direction tsc leaves open by reading the source
 * text, since `DigiChatContainer` is a Cloudflare Container (Durable Object) and
 * is not constructible outside the Workers runtime.
 *
 * index.ts aliases the `cloudflare:workers` `env` binding to the local
 * `workerVars` const, so the reference accessor here is `workerVars.` (both
 * `workerVars` and `env` are accepted below, so a rename cannot silently make
 * every assertion vacuous -- the non-empty guard in "reads no undeclared" fails
 * loudly instead).
 *
 * `.test.ts`, not `.js`: vitest.config.ts includes only `.test.ts` files under
 * src, and tsconfig already covers src TypeScript sources. The `node` type
 * reference is what lets `node:fs`/`__dirname` typecheck, mirroring
 * embed-flag.test.ts in this same directory.
 */

const indexSource = readFileSync(join(__dirname, "index.ts"), "utf-8");

/**
 * `Env` members the Worker reads but deliberately does NOT forward under their
 * own name, with the reason each is exempt. One-way: listed names must be real
 * `Env` members, and must not appear as an `envVars` key (both asserted below).
 *
 * - `DIGICHAT_LEGACY_EMBED_ENABLED` is the documented opt-in flag; the Worker
 *   folds it (with the deprecated `DIGICHAT_EMBED_ENABLED` alias) into the single
 *   canonical `DIGICHAT_EMBED_ENABLED` the container receives via
 *   `legacyEmbedEnabledValue`. Forwarding the raw input too would let the
 *   container observe a flag the Worker already resolved to off.
 */
const WORKER_ONLY_ENV_MEMBERS: Record<string, string> = {
  DIGICHAT_LEGACY_EMBED_ENABLED:
    "resolved into the forwarded DIGICHAT_EMBED_ENABLED; never forwarded itself",
};

/**
 * Vars documented as optional Worker secrets in wrangler.toml but intentionally
 * NEITHER declared on `Env` NOR forwarded into the container. Their absence from
 * both lists is asserted, so re-adding one to either side trips this test and
 * forces a deliberate decision instead of an accidental reintroduction.
 *
 * - `DIGICHAT_DATABASE_URL` (audit D5): the Cloudflare deployment is DB-less --
 *   no Postgres instance or secret is provisioned. The digichat process treats
 *   it as optional (`getDb()` returns null; `/api/health` reports
 *   `database: skipped`; threads stay in localStorage). See the wrangler.toml
 *   note. The in-container consumer is documented, so this is a decision, not an
 *   oversight.
 */
const DOCUMENTED_NOT_FORWARDED: Record<string, string> = {
  DIGICHAT_DATABASE_URL:
    "Cloudflare container is intentionally DB-less; wrangler.toml documents it optional-only",
};

/** Throws (rather than matching nothing) so a re-indented or renamed block fails loudly. */
function extractEnvVarsBlock(source: string): string {
  const match = source.match(/envVars = \{([\s\S]*?)\n {2}\};/);
  if (!match) {
    throw new Error("could not locate the `envVars = { ... };` block in index.ts");
  }
  return match[1];
}

/** `workerVars.X` (the alias of `env`) reads inside the block, in source order. */
function extractEnvVarsRefs(body: string): string[] {
  return [...body.matchAll(/(?<![A-Za-z0-9_])(?:workerVars|env)\.([A-Za-z0-9_]+)/g)].map(
    (m) => m[1],
  );
}

/** Top-level `envVars` keys, matched at exactly 4-space indent (continuation lines indent deeper). */
function extractEnvVarsKeys(body: string): string[] {
  return [...body.matchAll(/^ {4}([A-Za-z_][A-Za-z0-9_]*):/gm)].map((m) => m[1]);
}

/**
 * Pairs each top-level key with the `workerVars.*` member(s) its OWN entry reads,
 * so a key can never borrow a neighboring entry's reference. Entries with no read
 * at all are omitted.
 */
function extractEnvVarsKeyToRefs(body: string): { key: string; refs: string[] }[] {
  const keyMatches = [...body.matchAll(/^ {4}([A-Za-z_][A-Za-z0-9_]*):/gm)];
  return keyMatches.map((match, i) => {
    const key = match[1];
    const entryStart = match.index + match[0].length;
    const entryEnd = i + 1 < keyMatches.length ? keyMatches[i + 1].index : body.length;
    return { key, refs: extractEnvVarsRefs(body.slice(entryStart, entryEnd)) };
  });
}

/** Only `string` members are forwarded env vars; `DIGICHAT` is the DurableObjectNamespace binding. */
function extractEnvInterfaceStringMembers(source: string): string[] {
  const block = source.match(/export interface Env \{([\s\S]*?)\n\}/);
  if (!block) {
    throw new Error("could not locate the `export interface Env { ... }` block in index.ts");
  }
  return [...block[1].matchAll(/^\s*([A-Za-z_][A-Za-z0-9_]*)\??:\s*string;/gm)].map((m) => m[1]);
}

const envBody = extractEnvVarsBlock(indexSource);
const envMembers = extractEnvInterfaceStringMembers(indexSource);
const forwardedKeys = extractEnvVarsKeys(envBody);

describe("digichat Env / envVars parity", () => {
  it("forwards every string member of Env through envVars, or documents why not", () => {
    const forwarded = new Set(forwardedKeys);
    const missing = envMembers.filter(
      (name) => !forwarded.has(name) && !(name in WORKER_ONLY_ENV_MEMBERS),
    );
    expect(
      missing,
      `Env member(s) declared but never keyed in envVars: ${missing.join(", ")}`,
    ).toEqual([]);
  });

  it("keeps the worker-only allowlist honest and one-way", () => {
    const declared = new Set(envMembers);
    const forwarded = new Set(forwardedKeys);
    const stale = Object.keys(WORKER_ONLY_ENV_MEMBERS).filter((name) => !declared.has(name));
    const leaked = Object.keys(WORKER_ONLY_ENV_MEMBERS).filter((name) => forwarded.has(name));
    expect(stale, `allowlisted but no longer on Env: ${stale.join(", ")}`).toEqual([]);
    expect(leaked, `worker-only var(s) forwarded into envVars: ${leaked.join(", ")}`).toEqual([]);
  });

  it("keys envVars only with names declared on Env", () => {
    const declared = new Set(envMembers);
    const undeclared = forwardedKeys.filter((name) => !declared.has(name));
    expect(
      undeclared,
      `envVars key(s) not declared on Env: ${undeclared.join(", ")}`,
    ).toEqual([]);
  });

  it("reads no undeclared workerVars in envVars", () => {
    const refs = extractEnvVarsRefs(envBody);
    // Guards against a vacuous pass if the accessor alias is renamed again.
    expect(refs.length, "no `workerVars.*`/`env.*` reads found in the envVars block").toBeGreaterThan(
      0,
    );
    const declared = new Set(envMembers);
    const undeclared = refs.filter((name) => !declared.has(name));
    expect(
      undeclared,
      `envVars reads undeclared var(s): ${undeclared.join(", ")}`,
    ).toEqual([]);
  });

  it("forwards each envVars key under its own name", () => {
    // A typo'd key such as `DIGICHAT_EMBED_TENANT: workerVars.DIGICHAT_EMBED_TENANTS`
    // leaves the ref present (passing the flat checks above) while the container
    // never receives DIGICHAT_EMBED_TENANTS. Requiring the key to appear among its
    // own entry's refs still permits a deliberate transform that reads itself.
    const mismatched = extractEnvVarsKeyToRefs(envBody)
      .filter(({ key, refs }) => refs.length > 0 && !refs.includes(key))
      .map(({ key, refs }) => `${key} reads ${refs.join("/")}`);
    expect(
      mismatched,
      `envVars key(s) whose name is not among the refs they read: ${mismatched.join(", ")}`,
    ).toEqual([]);
  });

  it("keeps documented-not-forwarded vars out of both Env and envVars", () => {
    const declared = new Set(envMembers);
    const forwarded = new Set(forwardedKeys);
    for (const name of Object.keys(DOCUMENTED_NOT_FORWARDED)) {
      expect(declared.has(name), `${name} unexpectedly declared on Env`).toBe(false);
      expect(forwarded.has(name), `${name} unexpectedly forwarded in envVars`).toBe(false);
    }
  });
});
