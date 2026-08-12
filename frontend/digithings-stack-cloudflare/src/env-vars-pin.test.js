import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins `envVars` (the object forwarded into the Container's runtime env) against
 * the `Env` interface (the Worker's typed binding surface) in index.ts.
 *
 * These two lists are hand-kept in sync (see index.ts's block comment). A var in
 * `Env` but missing from `envVars` typechecks fine and silently never reaches the
 * container -- exactly the failure that blocked the Supabase path for months and
 * is blocker 3 of issue #2239. tsc alone cannot catch this direction: an unused
 * interface member is not a type error, only a var referenced in `envVars` that
 * is *not* declared on `Env` fails typecheck (`Property 'X' does not exist on
 * type 'Env'`). This test closes the direction tsc leaves open by reading the
 * source text directly, rather than instantiating `DigiStackContainer` (a
 * Cloudflare `Container`/Durable Object, not constructible outside the Workers
 * runtime).
 *
 * Deliberately plain `.js`, not `.ts`: `tsconfig.json` scopes `types` to
 * `@cloudflare/workers-types` only (a Workers project, no Node globals), so
 * `node:fs`/`node:path`/`node:url` have no ambient declarations here and adding
 * `@types/node` risks colliding with `workers-types`' own global ambient
 * declarations (both declare `fetch`, `Request`, `Response`, etc). `tsconfig.json`'s
 * `include` only matches TypeScript sources, so this file is invisible to
 * `tsc --noEmit`; vitest still runs it via the `.test.{ts,js}` glob in
 * `vitest.config.ts`.
 */

const indexSource = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "index.ts"),
  "utf-8",
);

function extractEnvVarsRefs(source) {
  const block = source.match(/envVars = \{([\s\S]*?)\n {2}\};/);
  if (!block) {
    throw new Error("could not locate the `envVars = { ... };` block in index.ts");
  }
  return [...block[1].matchAll(/env\.([A-Za-z0-9_]+)/g)].map((m) => m[1]);
}

function extractEnvInterfaceStringMembers(source) {
  const block = source.match(/export interface Env \{([\s\S]*?)\n\}/);
  if (!block) {
    throw new Error("could not locate the `export interface Env { ... }` block in index.ts");
  }
  // Only `string` members are env vars forwarded to the container. `STACK` is the
  // DurableObjectNamespace binding, not an env var, and is excluded by this pattern.
  return [...block[1].matchAll(/^\s*([A-Za-z_][A-Za-z0-9_]*)\??:\s*string;/gm)].map((m) => m[1]);
}

describe("Env / envVars parity", () => {
  it("forwards every string member of Env through envVars", () => {
    const envMembers = extractEnvInterfaceStringMembers(indexSource);
    const forwarded = new Set(extractEnvVarsRefs(indexSource));
    const missing = envMembers.filter((name) => !forwarded.has(name));
    expect(missing, `Env member(s) declared but never read via env.* in envVars: ${missing}`).toEqual(
      [],
    );
  });

  it("declares Env for every env.* var envVars reads", () => {
    // Redundant with tsc (a stray env.FOO not on Env fails typecheck), but pinned
    // here too so this test file alone documents -- and enforces -- both directions.
    const envMembers = new Set(extractEnvInterfaceStringMembers(indexSource));
    const forwarded = extractEnvVarsRefs(indexSource);
    const undeclared = forwarded.filter((name) => !envMembers.has(name));
    expect(
      undeclared,
      `envVars reads env.* var(s) not declared on Env: ${undeclared}`,
    ).toEqual([]);
  });
});
