/**
 * Paths digichat owns on digithings.ai (Pages owns the marketing site and the
 * invite-gated OCC shell at /chat/occ).
 * digithings + OCC (and future tenants) share one Container — tenant selection
 * is via /embed?host=… / X-Embed-Host, not separate Container instances.
 *
 * DIG-5121: the app itself is the canonical digichat surface and is served
 * under /chat (ADR 0018, GitHub #1252). The Container is BUILT with that base
 * path baked in, so the Worker maps every public path onto the path the
 * Container actually serves — see `containerPathFor`.
 */
import { isOccShellPath } from "./occ-gate";

/**
 * The base path the digichat app is built and served under inside the Container.
 *
 * Next bakes `basePath` at BUILD time (apps/digichat/next.config.ts reads
 * DIGICHAT_BASE_PATH), so this is the same value the image is built with
 * (infra/docker/Dockerfile.digichat-cloudflare). The contract test pins the two
 * together so the edge and the image cannot drift apart.
 *
 * /chat, not /digichat: the app's surface is the ROOT route
 * (apps/digichat/src/app/(digichat)/page.tsx) and there is no src/app/chat
 * directory, so a /chat base path does not nest into /chat/chat.
 */
export const CONTAINER_BASE_PATH = "/chat";

/**
 * The asset prefix the image is built with (DIGICHAT_ASSET_PREFIX).
 * Static assets are served from /_dtchat/* — outside the base path, because
 * Next maps the asset prefix back onto the base path internally.
 */
export const CONTAINER_ASSET_PREFIX = "/_dtchat";

/**
 * The container-local MCP prefix the in-container trusted proxy answers before
 * Next sees the request (apps/digichat/scripts/trusted-proxy-server.mjs). It
 * lives inside the Container, not under the public base path, so it is never
 * moved.
 */
export const CONTAINER_LOCAL_PREFIX = "/api/mcp/zammad";

/**
 * The container-local path for a request that addresses the in-container MCP
 * endpoint, or null when it does not.
 *
 * The endpoint has two spellings once the app is served under the base path:
 * the container-local one (/api/mcp/zammad/…, answered by the in-container
 * trusted proxy) and the base-path one (/chat/api/mcp/zammad/…, which Next's
 * own route would answer — and that route carries no auth of its own). Both
 * are container-local, and the base-path spelling is mapped back onto the
 * container-local one so the unauthenticated Next copy is never reached.
 *
 * The edge gate (src/index.ts) keys on this helper, so both spellings are
 * gated with the same edge key.
 */
export function containerLocalMcpPath(pathname: string): string | null {
  if (pathname === CONTAINER_LOCAL_PREFIX || pathname.startsWith(`${CONTAINER_LOCAL_PREFIX}/`)) {
    return pathname;
  }
  const underBase = `${CONTAINER_BASE_PATH}${CONTAINER_LOCAL_PREFIX}`;
  if (pathname === underBase || pathname.startsWith(`${underBase}/`)) {
    return `${CONTAINER_LOCAL_PREFIX}${pathname.slice(underBase.length)}`;
  }
  return null;
}

/**
 * Container-internal paths the app itself refuses in production.
 *
 * The devkit and baseline previews are local-only: their pages call
 * `notFound()` when NODE_ENV is production
 * (apps/digichat/src/app/(devkit)/devkit/page.tsx,
 * apps/digichat/src/app/(baseline)/baseline/page.tsx) and their API routes
 * are guarded by `isLocalBaselinePreview` (apps/digichat/src/lib/
 * baseline-preview.ts).
 *
 * Serving the app under /chat makes the whole /chat tree reachable from the
 * edge, so the edge refuses these too instead of relying on the app's own
 * guard being the only thing between the internet and a dev-only surface.
 */
export const CONTAINER_INTERNAL_PREFIXES = [
  "/devkit",
  "/baseline",
  "/api/devkit",
  "/api/baseline-chat",
];

/**
 * True for a container-internal path, in either spelling (with or without the
 * base path). Such a path is never proxied: the Worker answers 404.
 */
export function isContainerInternalPath(pathname: string): boolean {
  const relative = pathname.startsWith(`${CONTAINER_BASE_PATH}/`)
    ? pathname.slice(CONTAINER_BASE_PATH.length)
    : pathname;
  return CONTAINER_INTERNAL_PREFIXES.some(
    (prefix) => relative === prefix || relative.startsWith(`${prefix}/`),
  );
}

/**
 * True for the canonical /chat surface: the app itself, minus the invite-gated
 * OCC shell, which stays a Pages surface behind the gate.
 */
export function isChatSurfacePath(pathname: string): boolean {
  if (isOccShellPath(pathname)) return false;
  return pathname === CONTAINER_BASE_PATH || pathname.startsWith(`${CONTAINER_BASE_PATH}/`);
}

/**
 * True for the public paths this Worker forwards to the digichat Container.
 *
 * The canonical /chat surface is proxied (DIG-5121) except for the
 * invite-gated OCC shell, which stays a Pages surface behind the gate.
 */
export function shouldProxyToDigiChat(pathname: string): boolean {
  if (isChatSurfacePath(pathname)) return true;
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

/**
 * The path the Container serves for a given public path.
 *
 * The Container is built with `basePath: /chat`, and Next answers ONLY under
 * that prefix, so a request that reaches the Container has to carry the base
 * path exactly once:
 *
 *   - a path already under /chat is passed through unchanged;
 *   - the in-container MCP prefix is answered by the trusted proxy before Next
 *     sees it, so it is never moved — including its base-path spelling, which
 *     is mapped back onto the container-local one (see
 *     `containerLocalMcpPath`);
 *   - static assets keep the asset prefix they are served from (/_dtchat/*),
 *     because Next rewrites the asset prefix back onto the base path itself;
 *   - every other path — the legacy compatibility routes (/embed, /api/chat*,
 *     /api/embed*, /api/byok*, /api/plan-proof*, /api/health, /healthz) — is
 *     moved under the base path, so it keeps working after the move.
 */
export function containerPathFor(pathname: string): string {
  const containerLocalMcp = containerLocalMcpPath(pathname);
  if (containerLocalMcp) return containerLocalMcp;
  if (pathname === CONTAINER_BASE_PATH || pathname.startsWith(`${CONTAINER_BASE_PATH}/`)) {
    return pathname;
  }
  if (pathname === CONTAINER_ASSET_PREFIX || pathname.startsWith(`${CONTAINER_ASSET_PREFIX}/`)) {
    return pathname;
  }
  return `${CONTAINER_BASE_PATH}${pathname}`;
}

/**
 * The request the Container serves: same method, headers, body and query, with
 * the path moved onto the Container's base path (see `containerPathFor`).
 *
 * The URL is rewritten, not the path string alone, so the query string and
 * every header the edge set (host, cookies, the client IP) survive.
 */
export function withContainerPath(request: Request, pathname: string): Request {
  const target = new URL(request.url);
  target.pathname = containerPathFor(pathname);
  return new Request(target.toString(), request);
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
 * Verify with the Worker's own, auth-exempt meta route (it reports both the id
 * and the rev; it needs its zone route `digithings.ai/_digichat/meta` enabled
 * to be reachable from outside — see wrangler.toml):
 *   curl -s https://digithings.ai/_digichat/meta | jq -r .containerId
 */
export function sharedDigichatContainerId(rev?: string | null): string {
  const normalised = normaliseRev(rev);
  return normalised
    ? `${SHARED_DIGICHAT_ID_PREFIX}${normalised}`
    : LEGACY_SHARED_DIGICHAT_CONTAINER_ID;
}
