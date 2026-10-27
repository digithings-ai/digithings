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

// MCP-scoped vars (#3780 Task 8): these belonged to the retired
// DigiQuantMcpContainer.envVars. The Worker-native DigiQuantMcpAgent
// (DIG-2913) reads its data through the MARKET_DATA binding, so no container
// forwards them any more (the container was deleted in DIG-5558) — never
// duplicated into DigiStackContainer.envVars either.
const MCP_SCOPED_VARS = new Set([
  "DIGIQUANT_MCP_SCOPE",
  "DIGIQUANT_MARKET_DATA_BACKEND",
  "R2_ACCOUNT_ID",
  "R2_BUCKET",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
]);

// Digichat-scoped vars (#4689): these belonged to the retired
// DigiChatContainer.envVars. They must stay out of every remaining container
// block (the stack container runs digikey/digigraph/digisearch, never the Next
// process; the MCP container runs digiquant-mcp). DIGIKEY_BFF_TOKEN is
// legitimately shared with the stack container, so it is not in this set.
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
  "DIGICHAT_MONITOR_TOKENS",
  "DIGICHAT_DASHBOARD_SUPABASE_URL",
  "DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY",
]);

// The fold's env surface, retired 2026-10-19. These names stay declared on
// `Env` because wrangler.toml still carries them for this Worker, but the
// DigiChatContainer that forwarded them is gone, so nothing keys them into an
// envVars block. Exempt from the forward-everything check; the scoping check
// below still refuses them in any remaining container's block.
const RETIRED_FOLD_VARS = new Set([...DIGICHAT_SCOPED_VARS, "DIGICHAT_LEGACY_EMBED_ENABLED"]);

// The retired digiquant-mcp container's env surface (DIG-5558). These names
// stay declared on `Env` because wrangler.toml still carries them for this
// Worker, but the DigiQuantMcpContainer that forwarded them is gone, so nothing
// keys them into an envVars block any more. Exempt from the forward-everything
// check; the scoping check below still refuses them in the remaining block.
const RETIRED_MCP_CONTAINER_VARS = new Set([
  ...MCP_SCOPED_VARS,
  "GLOOMBERB_SESSION_COOKIE",
]);


// Worker-scoped vars: read by the Worker's own request handling and
// deliberately NOT forwarded into any Container. `MARKET_DATA_ALLOWED_ORIGINS`
// gates CORS in src/market-data.ts's /v1/market/* handler (#4013 Task 8); no
// container process reads it, so keying it into an envVars block would repeat
// the dead-config duplication review finding 6 removed. Two-way pinned below:
// exempt from the forward-everything check, and refused if forwarded anyway.
// `MCP_EDGE_KEY` gates the Worker's /_stack/mcp/{digisearch,digivault} edge
// paths; the stack container's in-container MCP servers read their own env,
// never this key, so it stays Worker-scoped too.
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
  "MARKET_DATA_URL",
  "DASHBOARD_API_ALLOWED_ORIGINS",
  // DIG-3229: the deploying commit, injected at deploy time and read by the
  // Worker to derive the shared-stack Container id (ports.ts /
  // stackContainer() in index.ts). No container process ever reads this name --
  // forwarding it would put a Durable Object naming input into the container's
  // runtime env, where nothing consumes it.
  "STACK_CONTAINER_REV",
  // DIG-3585: /chat/occ invite gate. The container authorizes via the tenant
  // token, never this Worker secret.
  "OCC_INVITE_KEY",
  // DIG-3814: the deploying commit's short sha. The Worker uses it to derive the
  // folded digichat Container name (sharedDigichatContainerId, re-exported from
  // the standalone worker's own paths.ts), so the container process never sees it.
  "DIGICHAT_CONTAINER_REV",
  // The split corpus map's second half (2026-10-25): the Worker reads it to
  // compose the container's `DIGI_TENANT_CORPUS_MAP` via composeCorpusMap, and
  // the container process only ever reads the composed name -- forwarding the
  // raw half would put a 4.6 kB duplicate in the container env that nothing
  // consumes. Worker-scoped, not retired: it is live config, just not forwarded.
  "DIGI_TENANT_CORPUS_MAP_EXTRA",
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
      (name) =>
        !forwarded.has(name) &&
        !WORKER_SCOPED_VARS.has(name) &&
        !RETIRED_FOLD_VARS.has(name) &&
        !RETIRED_MCP_CONTAINER_VARS.has(name),
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

  it("keeps MCP-scoped vars out of every container block (the MCP container is gone)", () => {
    const blocks = extractAllEnvVarsBlocks(indexSource);
    // One envVars block remains: DigiStackContainer's. The MCP container's was
    // deleted with its class (DIG-5558), so its surface must not come back on
    // the surviving block.
    expect(blocks.length).toBe(1);
    const stackKeys = new Set(extractEnvVarsKeysFromBody(blocks[0]));
    // Name the remaining block, so a truncated or re-ordered extraction fails
    // here instead of making the absence check below vacuous.
    expect(stackKeys.has("DIGIVAULT_URL"), "blocks[0] is not DigiStackContainer").toBe(true);
    const resurrected = [...RETIRED_MCP_CONTAINER_VARS].filter((name) => stackKeys.has(name));
    expect(
      resurrected,
      `retired digiquant-mcp var(s) forwarded into a container envVars block: ${resurrected}`,
    ).toEqual([]);
  });

  it("keeps the retired digichat fold vars out of every remaining container block", () => {
    // The DigiChatContainer.envVars block was removed with the class
    // (2026-10-19). The fold's names may still be declared on Env because
    // wrangler.toml carries them, but no remaining container may forward one:
    // a key here with no container reading it is exactly the dead-config
    // duplication this file exists to catch.
    const blocks = extractAllEnvVarsBlocks(indexSource);
    expect(blocks.length).toBe(1);
    const stackKeys = new Set(extractEnvVarsKeysFromBody(blocks[0]));
    expect(stackKeys.has("DIGIVAULT_URL"), "blocks[0] is not DigiStackContainer").toBe(true);
    const leaked = [...DIGICHAT_SCOPED_VARS].filter((name) => stackKeys.has(name));
    expect(
      leaked,
      `retired digichat fold var(s) forwarded into a container envVars block: ${leaked}`,
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
