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
 * A key/value mismatch inside `envVars` -- e.g. `D1_ACCOUNT_1D: env.D1_ACCOUNT_ID
 * ?? ""` -- is a *third*, distinct failure neither of the two checks above would
 * catch: `env.D1_ACCOUNT_ID` still appears somewhere in the block (satisfying the
 * flat existence checks below), tsc accepts a free-form object-literal key, and
 * the container ends up with `D1_ACCOUNT_1D=""` and no `D1_ACCOUNT_ID` at all --
 * the exact production symptom this file exists to prevent, from a one-character
 * typo. `checkKeyMatchesRef` below closes that gap by pairing each key with the
 * `env.*` member its *own* entry reads, not just any `env.*` text anywhere in the
 * block.
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

// MCP-scoped vars (#3780 Task 8): forwarded by DigiQuantMcpContainer.envVars
// ONLY — never duplicated into DigiStackContainer.envVars (the stack container
// ignores them; duplication was removed in review finding 6). The first
// envVars block below is the stack container's, the second the MCP one's.
const MCP_SCOPED_VARS = new Set([
  "DIGIQUANT_MARKET_DATA_BACKEND",
  "FRED_API_KEY",
  "R2_ACCOUNT_ID",
  "R2_BUCKET",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
]);

// Deliberately throws rather than returning an empty match -- a re-indented
// `envVars = { ... };` (or `Env { ... }`) block must fail loudly, not silently
// pass every assertion below with zero entries extracted.
function extractAllEnvVarsBlocks(source) {
  const blocks = [...source.matchAll(/envVars = \{([\s\S]*?)\n {2}\};/g)].map(
    (m) => m[1],
  );
  if (blocks.length === 0) {
    throw new Error("could not locate the `envVars = { ... };` block in index.ts");
  }
  return blocks;
}

function extractEnvVarsBlock(source) {
  return extractAllEnvVarsBlocks(source)[0];
}

function extractEnvVarsRefsFromBody(body) {
  return [...body.matchAll(/env\.([A-Za-z0-9_]+)/g)].map((m) => m[1]);
}

function extractEnvVarsRefs(source) {
  return extractAllEnvVarsBlocks(source).flatMap(extractEnvVarsRefsFromBody);
}

/**
 * Pairs each top-level `envVars` key with the `env.*` member *its own entry*
 * reads -- scoped from just after that key's `:` to the start of the next
 * top-level key (or the end of the block), so a key can never pick up a
 * neighboring entry's reference the way a block-wide regex would. Entries with
 * no `env.*` read at all (e.g. `DIGIKEY_JWKS_URL`'s hardcoded default) are
 * omitted -- there is nothing to pin for those.
 *
 * Top-level keys are matched at exactly 4-space indent (`envVars`'s own entry
 * indent). Multi-line entries (e.g. `DIGI_TENANT_CORPUS_MAP`'s wrapped default)
 * indent their continuation past 4 spaces, so this does not mistake a
 * continuation line -- or a key-looking substring inside a quoted JSON
 * default -- for a new top-level key.
 */
function extractEnvVarsKeyToRefFromBody(body) {
  const keyMatches = [...body.matchAll(/^ {4}([A-Za-z_][A-Za-z0-9_]*):/gm)];
  return keyMatches
    .map((match, i) => {
      const key = match[1];
      const entryStart = match.index + match[0].length;
      const entryEnd = i + 1 < keyMatches.length ? keyMatches[i + 1].index : body.length;
      const ref = body.slice(entryStart, entryEnd).match(/env\.([A-Za-z0-9_]+)/);
      return ref ? { key, ref: ref[1] } : null;
    })
    .filter((pair) => pair !== null);
}

function extractEnvVarsKeyToRef(source) {
  return extractAllEnvVarsBlocks(source).flatMap(extractEnvVarsKeyToRefFromBody);
}

function extractEnvVarsKeysFromBody(body) {
  return [...body.matchAll(/^ {4}([A-Za-z_][A-Za-z0-9_]*):/gm)].map((m) => m[1]);
}

function extractEnvVarsKeys(source) {
  return extractAllEnvVarsBlocks(source).flatMap(extractEnvVarsKeysFromBody);
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
    // Compare Env members to top-level envVars *keys* (not arbitrary env.*
    // references elsewhere in the block). A typo'd key that still reads
    // env.FOO would pass a refs-only check while never forwarding FOO.
    // Union of both containers' blocks: MCP-scoped vars live on the MCP
    // block only (see the duplication check below).
    const envMembers = extractEnvInterfaceStringMembers(indexSource);
    const forwarded = new Set(extractEnvVarsKeys(indexSource));
    const missing = envMembers.filter((name) => !forwarded.has(name));
    expect(missing, `Env member(s) declared but never keyed in envVars: ${missing}`).toEqual(
      [],
    );
  });

  it("keeps MCP-scoped vars on the MCP container block only", () => {
    const blocks = extractAllEnvVarsBlocks(indexSource);
    expect(blocks.length).toBe(2);
    const stackKeys = new Set(extractEnvVarsKeysFromBody(blocks[0]));
    const mcpKeys = new Set(extractEnvVarsKeysFromBody(blocks[1]));
    const duplicated = [...MCP_SCOPED_VARS].filter((name) => stackKeys.has(name));
    expect(
      duplicated,
      `MCP-scoped var(s) duplicated into DigiStackContainer.envVars: ${duplicated}`,
    ).toEqual([]);
    const mcpMissing = [...MCP_SCOPED_VARS].filter((name) => !mcpKeys.has(name));
    expect(
      mcpMissing,
      `MCP-scoped var(s) missing from DigiQuantMcpContainer.envVars: ${mcpMissing}`,
    ).toEqual([]);
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

  it("forwards each envVars key under its own matching env.* name", () => {
    // Neither check above inspects *which* key a given `env.*` read sits next
    // to -- both are flat, block-wide existence checks. A typo'd key such as
    // `D1_ACCOUNT_1D: env.D1_ACCOUNT_ID ?? ""` still leaves `env.D1_ACCOUNT_ID`
    // in the block (passing both checks above) while the container never
    // receives `D1_ACCOUNT_ID` at all. This check pairs key and ref per entry
    // to catch exactly that.
    const pairs = extractEnvVarsKeyToRef(indexSource);
    const mismatched = pairs
      .filter(({ key, ref }) => key !== ref)
      .map(({ key, ref }) => `${key} reads env.${ref}`);
    expect(
      mismatched,
      `envVars key(s) whose name does not match the env.* member they read: ${mismatched}`,
    ).toEqual([]);
  });
});
