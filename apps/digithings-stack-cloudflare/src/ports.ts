/** digigraph default edge port inside the Profile A stack Container. */
export const DIGIGRAPH_PORT = 8000;

/** digikey edge port inside the Profile A stack Container. */
export const DIGIKEY_PORT = 8005;

/**
 * digisearch edge port inside the Profile A stack Container. Hosted on
 * search.digithings.ai (#4063) for CI web grounding, behind a digikey JWT
 * scoped `digisearch:query` — never anonymous.
 */
export const DIGISEARCH_PORT = 8002;

/**
 * digiquant-mcp market-data edge port (dedicated Container, #3780 Task 8).
 * Matches DIGIQUANT_MCP_PORT in digiquant/Dockerfile.mcp and the
 * streamable-http default in digiquant/src/digiquant/mcp_server.py.
 */
export const DIGIQUANT_MCP_PORT = 8767;

/** Reserved public hostname for the hosted market-data MCP server. */
export const DIGIQUANT_MCP_HOSTNAME = "mcp.digithings.ai";

/**
 * Durable Object / Container id for the dedicated digiquant-mcp instance.
 * Single pinned id on purpose: the MCP read path assumes a single replica
 * (in-memory 900s TTL cache), so this container runs max_instances = 1.
 */
export const MCP_CONTAINER_ID = "mcp-v1";

/**
 * Single Durable Object / Container id for the shared Profile A stack.
 *
 * DERIVED FROM THE DEPLOYING COMMIT, NOT HAND-EDITED (DIG-3229).
 * `sharedStackContainerId()` below builds the id from the `STACK_CONTAINER_REV`
 * Worker var, which `scripts/deploy.mjs` injects as
 * `wrangler deploy --var STACK_CONTAINER_REV:<sha12>`. Every deploy therefore
 * addresses a different Durable Object id, so every deploy guarantees a fresh
 * Firecracker instance instead of hoping the platform retires the old one.
 *
 * Why this was a hand-edited string, and what forgetting it already cost:
 * `sleepAfter` alone does not evict a Container under steady traffic, so a
 * code-only redeploy left the old instance — serving its old image — in place
 * indefinitely, and bumping this id was the only containment. It was forgotten
 * twice:
 *   - v16 → v17 (2026-10-06, DIG-1506 / DIG-1500): a v16 instance kept serving
 *     an image whose boot chain still re-ingested the committed `occ_tickets`
 *     PII snapshot on every cold start. Container disk is ephemeral, so the fix
 *     in #5192 (payload + fan-out retired) only reached the store once every
 *     instance id that could hold the old image was retired.
 *   - v17 → v18 (2026-10-08, digikey hotfix #5283 / #5010): a v17 instance kept
 *     serving the digikey build whose `_one_required` let a requested `ns:*`
 *     scope be satisfied by any narrow `ns:x` grant (scope escalation on both
 *     token exchanges). Under steady traffic a v17 instance never reached
 *     `sleepAfter`, so the Worker redeploy alone did not take the old scopes.py
 *     out of service.
 * Both fixes were real and both spent time "deployed but not in service"
 * because nobody remembered this line. There is nothing left to remember.
 *
 * Cost, stated plainly: the id now changes on EVERY deploy, including one that
 * touches only Worker code and no image. That costs one extra Container cold
 * start per deploy — the same cost the manual bump carried — and with
 * `sleepAfter = "1m"` that container is asleep for most of the day anyway.
 *
 * Rollback for a bad deploy: redeploy the previous commit and the id follows
 * it back. No migration, schema, or binding change is involved; the id is a
 * Durable Object name only.
 *
 * Verify after a deploy (this is what `scripts/deploy.mjs` checks):
 *   curl -sf https://graph.digithings.ai/_stack/meta | python3 -c
 *   'import sys,json;d=json.load(sys.stdin);print(d["containerId"],d["stackRev"])'
 */
export const LEGACY_SHARED_STACK_CONTAINER_ID = "shared-v18";

/**
 * Worker var carrying the deploying commit, injected by `scripts/deploy.mjs`
 * as `wrangler deploy --var STACK_CONTAINER_REV:<sha12>`. It is a Worker
 * variable rather than a build-time define on purpose: wrangler 4.133.0's
 * `--define` is broken and rejects every form, including `--define=FOO=bar`
 * (it hands the raw `KEY=VALUE` string to esbuild as an object key), so there
 * is no working substitution hook to use.
 *
 * Deliberately NOT declared in `wrangler.toml [vars]`: unset is the honest
 * state for a build that did not inject a rev (a CI `wrangler deploy
 * --dry-run`, or a deploy that bypassed `npm run deploy`), and the fallback
 * below reproduces today's id exactly. Adding a placeholder would both lie and
 * pull this key into the config-contract and self-host parity gates, which pin
 * every `[vars]` entry. Inject it; never hand-write it.
 */
export const STACK_CONTAINER_REV_VAR = "STACK_CONTAINER_REV";

/** DO name prefix. Kept so `_stack/meta` output stays recognisable. */
const SHARED_STACK_ID_PREFIX = "shared-";

/** Longest rev kept in the id; a full sha is 40, the wrapper passes 12. */
const MAX_REV_LEN = 40;

/**
 * Normalise a rev into the Durable Object name alphabet: lowercase alphanumerics
 * only, trimmed, capped. A rev is a git sha, so this is defence in depth — it
 * exists so nothing that reaches the id (a stray flag, a shell alias) can inject
 * characters into a name that decides which instance serves traffic.
 */
function normaliseRev(rev: string | undefined): string {
  return (rev ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^0-9a-z]/g, "")
    .slice(0, MAX_REV_LEN);
}

/**
 * The normalised deploy rev, or null when there is none. Null means "fall
 * back", not "error": a CI dry run and a deploy that bypassed `npm run deploy`
 * both land here, and both reproduce today's id rather than inventing a new one.
 */
export function stackContainerRev(rev?: string): string | null {
  const normalised = normaliseRev(rev);
  return normalised === "" ? null : normalised;
}

/**
 * Durable Object / Container id for the shared Profile A stack, derived from the
 * deploying commit. `rev` is the `STACK_CONTAINER_REV` Worker var; passing
 * nothing yields the legacy fallback, which is why index.ts reaches this through
 * the single `stackContainer()` helper rather than per call site.
 */
export function sharedStackContainerId(rev?: string): string {
  const normalised = stackContainerRev(rev);
  return normalised === null
    ? LEGACY_SHARED_STACK_CONTAINER_ID
    : SHARED_STACK_ID_PREFIX + normalised;
}

/**
 * Map public hostname → container port.
 * Unknown hosts return null (Worker responds 404).
 */
export function portForHostname(hostname: string): number | null {
  const host = hostname.trim().toLowerCase();
  if (host === "graph.digithings.ai" || host.startsWith("graph.")) {
    return DIGIGRAPH_PORT;
  }
  if (host === "key.digithings.ai" || host.startsWith("key.")) {
    return DIGIKEY_PORT;
  }
  if (host === "search.digithings.ai" || host.startsWith("search.")) {
    return DIGISEARCH_PORT;
  }
  // wrangler.dev / workers.dev fallback: path-prefix routing not used;
  // default to digigraph so /healthz works on the workers.dev URL.
  if (host.endsWith(".workers.dev") || host === "localhost" || host === "127.0.0.1") {
    return DIGIGRAPH_PORT;
  }
  return null;
}
