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
// envVars block below is the stack container's, the second the MCP one's,
// the third the digichat one's (#4689).
const MCP_SCOPED_VARS = new Set([
  "DIGIQUANT_MCP_SCOPE",
  "DIGIQUANT_MARKET_DATA_BACKEND",
  "FRED_API_KEY",
  "R2_ACCOUNT_ID",
  "R2_BUCKET",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
]);

// Digichat-scoped vars (#4689): forwarded by DigiChatContainer.envVars ONLY —
// never duplicated into DigiStackContainer.envVars (the stack container runs
// digikey/digigraph/digisearch, never the Next process). Exception:
// DIGIKEY_BFF_TOKEN is legitimately shared (both containers read it), so it
// is not in this set. Pinned present on the digichat block and absent from
// the stack block below.
const DIGICHAT_SCOPED_VARS = new Set([
  "DIGICHAT_EMBED_ENABLED",
  "DIGICHAT_REQUIRE_ROOT_AUTH",
  "DIGICHAT_EMBED_HOSTS",
  "DIGICHAT_AUTO_MIGRATE",
  "DIGICHAT_TRUSTED_PROXIES",
  "DIGICHAT_ENABLED_SERVICES",
  "AUTH_SECRET",
  "DIGICHAT_EMBED_TENANTS",
  "DIGIGRAPH_INTERNAL_URL",
  "DIGIKEY_URL",
  "DIGICHAT_PLAN_PROOF_SECRET",
  "DIGICHAT_DASHBOARD_SUPABASE_URL",
  "DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY",
]);

// Worker-scoped vars: read by the Worker's own request handling and
// deliberately NOT forwarded into any Container. `MARKET_DATA_ALLOWED_ORIGINS`
// gates CORS in src/market-data.ts's /v1/market/* handler (#4013 Task 8); no
// container process reads it, so keying it into an envVars block would repeat
// the dead-config duplication review finding 6 removed. Two-way pinned below:
// exempt from the forward-everything check, and refused if forwarded anyway.
// `MCP_EDGE_KEY` gates the Worker's /_stack/mcp/zammad edge path; the stack
// container's zammad-mcp process reads its own ZAMMAD_API_TOKEN, never this
// key, so it stays Worker-scoped too.
const WORKER_SCOPED_VARS = new Set([
  "MARKET_DATA_ALLOWED_ORIGINS",
  "MCP_EDGE_KEY",
  "MCP_EDGE_KEYS",
  // Folded dashboard-api (#4687): read by the Worker's own /dashboard-api/*
  // handler (src/dashboard-api.ts forwards worker env to the folded route
  // code); no container process reads them, so they stay Worker-scoped like
  // MARKET_DATA_ALLOWED_ORIGINS above.
  "SUPABASE_URL",
  "SUPABASE_SERVICE_ROLE_KEY",
  // Canonical anon key (#4700): same-worker fallback source for the legacy
  // digichat forward; no container reads this name directly.
  "SUPABASE_ANON_KEY",
  "MARKET_DATA_URL",
  "DASHBOARD_API_ALLOWED_ORIGINS",
  // Folded digichat (#4689): DIGICHAT_LEGACY_EMBED_ENABLED is folded into the
  // forwarded DIGICHAT_EMBED_ENABLED at Worker evaluation time (see the
  // DigiChatContainer.envVars entry); the container never sees this name, so
  // it stays Worker-scoped. (The deprecated DIGICHAT_EMBED_ENABLED alias IS a
  // forwarded key, like on the standalone worker.)
  "DIGICHAT_LEGACY_EMBED_ENABLED",
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
    const missing = envMembers.filter(
      (name) => !forwarded.has(name) && !WORKER_SCOPED_VARS.has(name),
    );
    expect(missing, `Env member(s) declared but never keyed in envVars: ${missing}`).toEqual(
      [],
    );
  });

  it("keeps worker-scoped vars out of every container's envVars", () => {
    // The exemption above must stay one-way: a var the Worker consumes is not
    // container runtime env, and forwarding it is the typo/duplication class
    // this file exists to catch, just in the opposite direction.
    const forwarded = new Set(extractEnvVarsKeys(indexSource));
    const leaked = [...WORKER_SCOPED_VARS].filter((name) => forwarded.has(name));
    expect(
      leaked,
      `worker-scoped var(s) forwarded into a container envVars block: ${leaked}`,
    ).toEqual([]);
  });

  it("keeps MCP-scoped vars on the MCP container block only", () => {
    const blocks = extractAllEnvVarsBlocks(indexSource);
    expect(blocks.length).toBe(3);
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

  it("keeps digichat-scoped vars on the digichat container block only", () => {
    const blocks = extractAllEnvVarsBlocks(indexSource);
    expect(blocks.length).toBe(3);
    const stackKeys = new Set(extractEnvVarsKeysFromBody(blocks[0]));
    const chatKeys = new Set(extractEnvVarsKeysFromBody(blocks[2]));
    const duplicated = [...DIGICHAT_SCOPED_VARS].filter((name) => stackKeys.has(name));
    expect(
      duplicated,
      `digichat-scoped var(s) duplicated into DigiStackContainer.envVars: ${duplicated}`,
    ).toEqual([]);
    const chatMissing = [...DIGICHAT_SCOPED_VARS].filter((name) => !chatKeys.has(name));
    expect(
      chatMissing,
      `digichat-scoped var(s) missing from DigiChatContainer.envVars: ${chatMissing}`,
    ).toEqual([]);
  });

  it("falls back to canonical Supabase names for legacy digichat dashboard keys", () => {
    // #4700: the DIGICHAT_DASHBOARD names are legacy duplicates; the container
    // must keep working once the old secrets are deleted post-deploy, so both
    // entries pin the old-name-first, canonical-second chain.
    const blocks = extractAllEnvVarsBlocks(indexSource);
    const chatBody = blocks[2];
    const urlStart = chatBody.indexOf("DIGICHAT_DASHBOARD_SUPABASE_URL:");
    const anonStart = chatBody.indexOf("DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY:");
    expect(urlStart).toBeGreaterThan(-1);
    expect(anonStart).toBeGreaterThan(urlStart);
    expect(chatBody.slice(urlStart, anonStart)).toMatch(
      /env\.DIGICHAT_DASHBOARD_SUPABASE_URL \?\? env\.SUPABASE_URL \?\? ""/,
    );
    expect(chatBody.slice(anonStart)).toMatch(
      /env\.DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY \?\? env\.SUPABASE_ANON_KEY \?\? ""/,
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
