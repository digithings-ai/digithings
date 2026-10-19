/**
 * Paths digichat owns on digithings.ai (Pages owns /chat and marketing).
 * digithings + OCC (and future tenants) share one Container — tenant selection
 * is via /embed?host=… / X-Embed-Host, not separate Container instances.
 */
export function shouldProxyToDigiChat(pathname: string): boolean {
  return (
    pathname === "/embed" ||
    pathname.startsWith("/embed/") ||
    pathname === "/api/chat" ||
    pathname.startsWith("/api/chat/") ||
    pathname.startsWith("/api/embed/") ||
    pathname.startsWith("/api/byok/") ||
    pathname === "/api/plan-proof" ||
    pathname.startsWith("/api/plan-proof/") ||
    pathname === "/api/health" ||
    pathname === "/healthz" ||
    pathname.startsWith("/_dtchat/")
  );
}

/** Every shared Container id starts here. */
const SHARED_DIGICHAT_ID_PREFIX = "shared-";

/** Defence in depth: nothing longer can reach a Durable Object name. */
const MAX_REV_LEN = 40;

/**
 * Container id used by a deploy that carried no `DIGICHAT_CONTAINER_REV`.
 *
 * That state is honest, not a defect: it is what a bare `npx wrangler deploy`
 * produces, and what the stock bundle falls back to when the Worker var is
 * unset. It reproduces the id this file was hand-pinned to before the
 * derivation landed ("shared-v10"), so a fallback deploy keeps addressing the
 * instance that is already warm instead of silently orphaning it.
 *
 * Do NOT put this id back in `[vars]`, and do NOT hand-bump it. Inject
 * `DIGICHAT_CONTAINER_REV` instead — see `scripts/deploy.mjs`.
 */
export const LEGACY_SHARED_DIGICHAT_CONTAINER_ID = "shared-v10";

/**
 * Worker var carrying the deploying commit's short sha, injected at deploy time
 * by `scripts/deploy.mjs` (`--var DIGICHAT_CONTAINER_REV:<sha12>`).
 *
 * Deliberately NOT declared in wrangler.toml `[vars]`. Unset must keep meaning
 * "this deploy carried no rev" — a committed placeholder would both lie about
 * most deploys and pull this key into the config-contract and self-host parity
 * gates, which pin every `[vars]` entry. Inject it; never hand-write it.
 */
export const DIGICHAT_CONTAINER_REV_VAR = "DIGICHAT_CONTAINER_REV";

/** A git sha as it may appear in an id: 7-40 lowercase hex, nothing else. */
const REV_SHAPE = /^[0-9a-f]{7,40}$/;

/**
 * The rev as it will appear inside the id, or `""` when it is not one.
 *
 * This string becomes part of a Durable Object name, so it is normalised and
 * then *verified* rather than merely sanitised. Stripping characters is not
 * enough: stripping `../../etc/passwd` yields `etcpasswd`, which is harmless as
 * a name but wrong in a much more expensive way — it mints a NEW instance for
 * every distinct malformed value, so a broken deploy would silently create
 * container after container instead of falling back to the one known id. An
 * unrecognised value is therefore not repaired, it is rejected.
 *
 * Case is folded and padding trimmed first, because a rev is read back from an
 * env var and either of those is a harmless formatting difference rather than
 * a different commit.
 */
function normaliseRev(rev?: string | null): string {
  const candidate = String(rev ?? "")
    .trim()
    .toLowerCase()
    .slice(0, MAX_REV_LEN);
  return REV_SHAPE.test(candidate) ? candidate : "";
}

/**
 * The rev this deploy carries, or `null` when there is none.
 *
 * `null` means "fall back", never "error" — the fallback is a working deploy,
 * just an unverifiable one, and `scripts/deploy.mjs` is what makes it loud.
 */
export function digichatContainerRev(rev?: string | null): string | null {
  return normaliseRev(rev) || null;
}

/**
 * The Durable Object / Container name for every marketing tenant, derived from
 * the deploying commit.
 *
 * The id used to be a hand-edited literal that every image-changing deploy had
 * to remember to bump: `sleepAfter` alone does not evict a Container under
 * steady traffic, so a code-only redeploy left the previous Firecracker
 * instance serving its old image — which is how a warm instance was already
 * the mitigation for a stale `DIGICHAT_EMBED_TENANTS` value (DIG-1381 Act B1).
 * Deriving the id from the commit removes the manual step rather than
 * documenting it.
 *
 * The cost is stated plainly: the id now changes on EVERY deploy, so each
 * deploy costs one extra Container cold start. The rollback is symmetric —
 * redeploy the previous commit and the id follows it back.
 *
 * Verify with:
 *   curl -s https://digithings.ai/_stack/meta | jq .digichatContainerId
 */
export function sharedDigichatContainerId(rev?: string | null): string {
  const normalised = normaliseRev(rev);
  return normalised
    ? `${SHARED_DIGICHAT_ID_PREFIX}${normalised}`
    : LEGACY_SHARED_DIGICHAT_CONTAINER_ID;
}
