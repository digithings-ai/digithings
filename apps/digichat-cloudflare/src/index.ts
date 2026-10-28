/**
 * digithings digichat — Worker fronting one Cloudflare Container.
 * Proxies /chat (the app), /embed, digichat APIs, and /_dtchat assets to the
 * digichat Node image.
 *
 * Website paths (different chats, same Container):
 *   digithings.ai/chat      → the digichat app (DIG-5121; built with basePath /chat)
 *   digithings.ai/chat/occ  → invite gate (this Worker) → the app's /chat/embed,
 *                             OCC tenant; its /chat/api/* calls are bound to the
 *                             invite here too (see bindOccApiCall)
 */
import { Container, getContainer } from "@cloudflare/containers";
import { env } from "cloudflare:workers";
import {
  DIGICHAT_CONTAINER_REV_VAR,
  digichatContainerRev,
  isContainerInternalPath,
  sharedDigichatContainerId,
  shouldProxyToDigiChat,
  withContainerPath,
} from "./paths";
import { MCP_KEY_HEADER, evaluateMcpGate } from "./mcp-gate";
import { legacyEmbedEnabledValue } from "./embed-flag";
import { resolveConfigYaml, resolveEmbedTenants } from "./tenants-kv";
import {
  bindOccApiCall,
  isChatApiPath,
  isOccShellPath,
  occEmbedGate,
  occGate,
  occInviteMaxAgeSeconds,
  type OccCookiePolicy,
  withoutInviteCookie,
} from "./occ-gate";
import { frameSafeErrorResponse } from "./frame-safe-error";
import { digichatContainerReset } from "./admin-reset";
import {
  CONTAINER_UNAVAILABLE_BODY,
  describeValue,
  fetchContainerWithRetry,
  NO_INSTANCE_STATUS,
  RETRY_AFTER_SECONDS,
} from "./container-retry";

/**
 * `env` from `cloudflare:workers` is untyped until `wrangler types` generates
 * `worker-configuration.d.ts`; the local `Env` interface is the intended shape.
 */
const workerVars = env as unknown as Env;

/**
 * Worker-owned, secret-gated recovery lever for the shared Container. Handled
 * here (never proxied to the container) so `destroy()` can reclaim an instance
 * that outlived its idle tail and still holds one of the Worker's container
 * slots (wrangler.toml allows two, so a stuck instance no longer starves
 * every cold start on its own).
 */
const DIGICHAT_ADMIN_RESET_PATH = "/_digichat-admin/container/reset";

/**
 * How long a resolved tenant registry + deployment document is reused before
 * KV is read again. The bound exists because a Container instance outlives a
 * Worker deploy: the container id is derived from the deploying commit, so a
 * redeploy of the same commit reuses the instance, its boot env, and a
 * "resolved once per boot" config — a KV edit then never reaches the container
 * at all. Short by design: it bounds how stale an edit can be, not how often an
 * operator edits.
 */
export const BOOT_CONFIG_TTL_MS = 30_000;

/**
 * True when a thrown value is an Error, asked in a way that cannot throw.
 *
 * `instanceof` walks the prototype chain, and a value that cannot be
 * inspected throws there. A guard that throws would turn a caught failure back
 * into an uncaught one, which is the failure this Worker exists to stop.
 */
function isRealError(value: unknown): boolean {
  try {
    return value instanceof Error;
  } catch {
    return false;
  }
}

export class DigiChatContainer extends Container {
  defaultPort = 3000;
  /**
   * Idle tail: each wake bills for the whole sleepAfter window. 5m (was 1m),
   * matching the stack: short enough that an idle or old-rev instance frees
   * its slot quickly, long enough that a reader pausing between turns does not
   * pay a cold start each time (t1702u).
   */
  sleepAfter = "5m";
  /**
   * Runtime env for the digichat Node process. Secrets come from
   * `wrangler secret put`; plain vars from wrangler.toml `[vars]`.
   * @see https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/
   */
  envVars = {
    // Legacy generic anonymous embed is OFF unless explicitly opted in via the
    // documented DIGICHAT_LEGACY_EMBED_ENABLED (or its deprecated alias).
    DIGICHAT_EMBED_ENABLED: legacyEmbedEnabledValue(
      workerVars.DIGICHAT_LEGACY_EMBED_ENABLED,
      workerVars.DIGICHAT_EMBED_ENABLED,
    ),
    DIGICHAT_REQUIRE_ROOT_AUTH: workerVars.DIGICHAT_REQUIRE_ROOT_AUTH ?? "0",
    DIGICHAT_EMBED_HOSTS:
      workerVars.DIGICHAT_EMBED_HOSTS ??
      "digithings.ai,www.digithings.ai,occ.digithings.ai,digiquant.io,www.digiquant.io",
    DIGICHAT_AUTO_MIGRATE: workerVars.DIGICHAT_AUTO_MIGRATE ?? "0",
    DIGICHAT_TRUSTED_PROXIES: workerVars.DIGICHAT_TRUSTED_PROXIES ?? "",
    // Profile A: digisearch lives loopback in digithings-stack; only probe digigraph.
    DIGICHAT_ENABLED_SERVICES: workerVars.DIGICHAT_ENABLED_SERVICES ?? "digigraph",
    AUTH_SECRET: workerVars.AUTH_SECRET ?? "",
    DIGICHAT_EMBED_TENANTS: workerVars.DIGICHAT_EMBED_TENANTS ?? "",
    // Deployment document (YAML/JSON text). Normally read from KV `config-yaml`
    // at boot and overwritten below; this var is the seam for `wrangler dev`
    // and for a deploy that pins the document in `[vars]`.
    DIGICHAT_CONFIG_YAML: workerVars.DIGICHAT_CONFIG_YAML ?? "",
    DIGIGRAPH_INTERNAL_URL: workerVars.DIGIGRAPH_INTERNAL_URL ?? "",
    DIGIKEY_URL: workerVars.DIGIKEY_URL ?? "",
    DIGIKEY_BFF_TOKEN: workerVars.DIGIKEY_BFF_TOKEN ?? "",
    // The chat's API-key MCP identity (digikey). The container mints edge
    // tokens from the BFF session first, because that token names the turn's
    // tenant; this key is only the fallback for a deployment without
    // DIGIKEY_BFF_TOKEN (its token carries the key's own tenant).
    DIGICHAT_MCP_IDENTITY_KEY: workerVars.DIGICHAT_MCP_IDENTITY_KEY ?? "",
    DIGICHAT_PLAN_PROOF_SECRET: workerVars.DIGICHAT_PLAN_PROOF_SECRET ?? "",
    DIGICHAT_MONITOR_TOKENS: workerVars.DIGICHAT_MONITOR_TOKENS ?? "",
    DIGICHAT_DASHBOARD_SUPABASE_URL: workerVars.DIGICHAT_DASHBOARD_SUPABASE_URL ?? "",
    DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY:
      workerVars.DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY ?? "",
    // Read-only Zammad helpdesk MCP (in-container zammad-mcp, OCC tickets).
    ZAMMAD_API_TOKEN: workerVars.ZAMMAD_API_TOKEN ?? "",
    ZAMMAD_BASE_URL: workerVars.ZAMMAD_BASE_URL ?? "",
    // Edge key for the digithings-stack `/_stack/mcp/<id>` routes that front
    // digisearch/digivault; matches the stack Worker's MCP_EDGE_KEY secret and
    // reaches the container as the `x-digi-mcp-key` header value. Set with
    // `wrangler secret put DIGICHAT_MCP_EDGE_KEY`, never in a document.
    DIGICHAT_MCP_EDGE_KEY: workerVars.DIGICHAT_MCP_EDGE_KEY ?? "",
  };

  /** When the current KV resolution was applied; null means "read again now". */
  private configResolvedAt: number | null = null;

  /**
   * The KV resolution in flight. Requests that arrive while one is running
   * await it instead of starting their own, so a burst costs one read per key
   * rather than one read per request.
   */
  private configResolution: Promise<void> | null = null;

  /**
   * Bumped by `onStop()`. A resolution that straddles a stop is discarded
   * rather than marking itself fresh against the boot that just ended.
   */
  private configEpoch = 0;

  /**
   * Resolve the tenant registry and the deployment document from KV and apply
   * them to the container's env. Never throws: both failures have a documented
   * fail-soft value, and this runs on the request path.
   *
   * Precedence is unchanged — `resolveEmbedTenants(kv, legacySecret, env)` then
   * `resolveConfigYaml(kv)`, with KV winning over the `[vars]` seam.
   */
  private async resolveBootConfig(epoch: number): Promise<void> {
    let tenants = "";
    try {
      const resolved = await resolveEmbedTenants(
        workerVars.DIGICHAT_TENANTS_KV,
        workerVars.DIGICHAT_EMBED_TENANTS,
        workerVars as unknown as Record<string, unknown>,
      );
      tenants = resolved.json;
      console.log(`[tenants-kv] embed tenants source=${resolved.source}`);
    } catch (e) {
      // A tenant-config failure must not 500 every proxied request (embed,
      // chat, assets, /healthz). Fail closed to no tenants for this window;
      // the next window retries, and onStop() re-arms immediately.
      console.error(`[tenants-kv] tenant config unavailable, serving no tenants: ${(e as Error).message}`);
    }
    // `resolveConfigYaml` never throws: a missing key or failed read is logged
    // there and leaves the container on its own file/defaults, which is the
    // documented precedence.
    const { yaml, source } = await resolveConfigYaml(workerVars.DIGICHAT_TENANTS_KV);
    console.log(`[config-kv] digichat config source=${source}`);
    // A stop overtook this read. Applying it would hand the next request a
    // value resolved against the boot that just ended, and would extend the
    // stale window by another TTL.
    if (epoch !== this.configEpoch) return;
    this.envVars = {
      ...this.envVars,
      DIGICHAT_EMBED_TENANTS: tenants,
      // KV wins over the `[vars]` seam; `none` leaves that seam in charge.
      ...(source === "kv" ? { DIGICHAT_CONFIG_YAML: yaml } : {}),
    };
    this.configResolvedAt = Date.now();
  }

  /**
   * One KV resolution per {@link BOOT_CONFIG_TTL_MS} window, shared by every
   * request inside it. `bootConfigResolved` used to be a one-shot latch, which
   * made a KV edit invisible until the container itself was recycled.
   */
  private async ensureBootConfig(): Promise<void> {
    if (this.configResolvedAt !== null && Date.now() - this.configResolvedAt < BOOT_CONFIG_TTL_MS) {
      return;
    }
    if (this.configResolution) return this.configResolution;
    const resolution = this.resolveBootConfig(this.configEpoch);
    this.configResolution = resolution;
    try {
      await resolution;
    } finally {
      // Only the resolution that owns the slot clears it: onStop() may already
      // have replaced it with a fresh one.
      if (this.configResolution === resolution) this.configResolution = null;
    }
  }

  /**
   * Before the container is asked for anything, make sure this window's
   * tenant registry and deployment document are resolved, then proxy.
   *
   * The config lives in KV, outside both the image and the Worker, so an
   * operator edit needs no redeploy of either half — it is picked up when the
   * window expires (or on the next request after `onStop()`).
   */
  override async fetch(request: Request): Promise<Response> {
    await this.ensureBootConfig();
    try {
      return await super.fetch(request);
    } catch (cause) {
      // The hop to the container rejected with a value that is not an Error.
      // The @cloudflare/containers package rethrows such a value verbatim, so
      // it would leave this Durable Object as an uncaught exception and the
      // Worker's own guard would never see it (run-watch DIG-4928). The client
      // is told to come back instead.
      //
      // A real error is rethrown unchanged: it carries a message, a stack and
      // a type, and the caller has to see it. A non-Error carries none of
      // them, so it is described in the log — the platform renders such a
      // value as it stands, so a thrown Date would leave nothing but a bare
      // date — and the answer says what happened instead.
      if (isRealError(cause)) throw cause;
      console.error(
        "digichat: container could not be reached: the container hop rejected with a value that is not an Error:",
        describeValue(cause),
      );
      return new Response(CONTAINER_UNAVAILABLE_BODY, {
        status: NO_INSTANCE_STATUS,
        headers: { "Retry-After": String(RETRY_AFTER_SECONDS) },
      });
    }
  }

  /**
   * Re-arm on stop: the DO outlives container sleeps, so the next request after
   * a stop re-reads KV even inside the TTL window. The epoch makes a read that
   * was already in flight when the stop landed discard itself.
   */
  override onStop(): void {
    this.configEpoch += 1;
    this.configResolvedAt = null;
    this.configResolution = null;
  }
}

/** The `occ_invite` cookie lifetime from the non-secret var (default 30 days). */
function occCookiePolicy(env: Env): OccCookiePolicy {
  return { maxAgeSeconds: occInviteMaxAgeSeconds(env.OCC_INVITE_MAX_AGE_DAYS) };
}

export interface Env {
  DIGICHAT: DurableObjectNamespace<DigiChatContainer>;
  /**
   * DIG-1210 invite key gating /chat/occ and binding the OCC page's
   * /chat/api/* calls to the invite. Worker-only; never forwarded.
   */
  OCC_INVITE_KEY?: string;
  /**
   * Non-secret: how many days an `occ_invite` cookie is honoured after the
   * invite link set it (whole days, 1-365; default 30). Worker-only.
   */
  OCC_INVITE_MAX_AGE_DAYS?: string;
  /**
   * Short sha of the deploying commit, injected by `scripts/deploy.mjs` via
   * `wrangler deploy --var DIGICHAT_CONTAINER_REV:<sha12>`. It names the
   * Container (see `sharedDigichatContainerId`), so the Worker reads it and
   * deliberately does NOT forward it — the container process has no use for the
   * commit that built it.
   */
  DIGICHAT_CONTAINER_REV?: string;
  /** Documented opt-in for the legacy generic anonymous embed. */
  DIGICHAT_LEGACY_EMBED_ENABLED?: string;
  /** @deprecated Use DIGICHAT_LEGACY_EMBED_ENABLED. */
  DIGICHAT_EMBED_ENABLED?: string;
  DIGICHAT_REQUIRE_ROOT_AUTH?: string;
  DIGICHAT_EMBED_HOSTS?: string;
  DIGICHAT_AUTO_MIGRATE?: string;
  DIGICHAT_TRUSTED_PROXIES?: string;
  DIGICHAT_ENABLED_SERVICES?: string;
  AUTH_SECRET?: string;
  DIGICHAT_EMBED_TENANTS?: string;
  /**
   * Deployment document (YAML or JSON text). Normally supplied at boot from
   * KV `config-yaml` in the DIGICHAT_TENANTS_KV namespace; a `[vars]` value is
   * the local-dev / pinned-document seam and loses to KV when both exist.
   */
  DIGICHAT_CONFIG_YAML?: string;
  /** KV with key `embed-tenants` (non-secret tenant config; refs via *Env). */
  DIGICHAT_TENANTS_KV?: KVNamespace;
  DIGIGRAPH_INTERNAL_URL?: string;
  DIGIKEY_URL?: string;
  DIGIKEY_BFF_TOKEN?: string;
  /** Dedicated digikey API key for MCP `authScheme: jwt` rows (server-only). */
  DIGICHAT_MCP_IDENTITY_KEY?: string;
  DIGICHAT_PLAN_PROOF_SECRET?: string;
  DIGICHAT_MONITOR_TOKENS?: string;
  DIGICHAT_DASHBOARD_SUPABASE_URL?: string;
  DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY?: string;
  /** Read-only Zammad helpdesk MCP: base URL + API token, forwarded to the container. */
  ZAMMAD_API_TOKEN?: string;
  ZAMMAD_BASE_URL?: string;
  /** Worker-only gate for /api/mcp/zammad*; never forwarded to the container. */
  ZAMMAD_EDGE_KEY?: string;
  /**
   * Key for the digithings-stack `/_stack/mcp/<id>` edge (digisearch/digivault);
   * forwarded to the container as `x-digi-mcp-key`. Same value as the stack
   * Worker's MCP_EDGE_KEY secret; set with `wrangler secret put`.
   */
  DIGICHAT_MCP_EDGE_KEY?: string;
  /**
   * Worker-only key for the container reset lever; never forwarded to the
   * container. Unset means the lever is off (the route answers 404).
   */
  DIGICHAT_ADMIN_KEY?: string;
}

export default {
  async fetch(request: Request, workerEnv: Env): Promise<Response> {
    const url = new URL(request.url);
    // Computed before the invite gate because /chat/occ is served by the same
    // container as /chat: the gate validates, then proxies there. The id is
    // derived from the deploy's rev, never hand-pinned.
    const containerId = sharedDigichatContainerId(workerEnv.DIGICHAT_CONTAINER_REV);
    if (isOccShellPath(url.pathname)) {
      // One gate, one secret, one path: the invite is checked here and the
      // request goes to the container's own embed route. Nothing is fetched
      // from this Worker's own URL, and Pages is not in the chain.
      //
      // The upstream is wrapped exactly like the /chat proxy above, so a
      // draining slot or a dropped connection on this path answers the same
      // retryable 503 / inline HTML `/chat` answers, instead of a raw 5xx.
      const container = getContainer(workerEnv.DIGICHAT, containerId);
      return occGate(
        request,
        workerEnv.OCC_INVITE_KEY,
        async (req) =>
          frameSafeErrorResponse(
            req,
            await fetchContainerWithRetry(req, (r) => container.fetch(r)),
          ),
        fetch,
        occCookiePolicy(workerEnv),
      );
    }
    // The /embed?host=<invite-only tenant> form without its key: the site 404,
    // byte-for-byte, before the container is ever asked.
    const embedGate = await occEmbedGate(request, workerEnv.OCC_INVITE_KEY);
    if (embedGate) return embedGate;
    // Worker-owned reset lever: intercepted here, before any container proxy,
    // and fail-closed with a 404 that never discloses the route. The instance
    // it destroys is the same derived id the proxy below addresses.
    if (url.pathname === DIGICHAT_ADMIN_RESET_PATH) {
      return digichatContainerReset(
        request,
        workerEnv.DIGICHAT_ADMIN_KEY,
        containerId,
        () => getContainer(workerEnv.DIGICHAT, containerId).destroy(),
      );
    }
    // Served by the Worker itself, never proxied: the id a deploy derived is
    // the only thing that makes a deploy verifiable rather than assumed, and
    // `/api/health` + `/healthz` are both digichat paths (proxied into the
    // container), so the Worker could not answer them.
    if (url.pathname === "/_digichat/meta") {
      return Response.json({
        ok: true,
        service: "digichat",
        containerId,
        rev: digichatContainerRev(workerEnv.DIGICHAT_CONTAINER_REV),
        revVar: DIGICHAT_CONTAINER_REV_VAR,
        note:
          "Worker up; the container may still be starting. rev: null means " +
          "this deploy carried no " +
          DIGICHAT_CONTAINER_REV_VAR +
          " and fell back to the legacy id.",
      });
    }
    // OCC helpdesk MCP: /api/mcp/zammad* is served by the in-container
    // zammad-mcp through the trusted proxy, not by Next. Gate it here with the
    // edge key this Worker holds; the container never sees the key. Fail closed.
    //
    // Both spellings are gated: the container-local one (/api/mcp/zammad/…) and
    // the base-path one (/chat/api/mcp/zammad/…), which the app's own Next
    // route would otherwise answer with no auth of its own (the in-image
    // trusted proxy only intercepts the container-local spelling). The helper
    // that recognises them also maps the base-path spelling back onto the
    // container-local one, so the unauthenticated copy is never reached.
    //
    // The verdict comes from the gate module (src/mcp-gate.ts), not from an
    // inline comparison: a gate that can only be READ cannot be proven
    // fail-closed, and the contract test executes this one.
    const mcpGate = evaluateMcpGate(
      url.pathname,
      request.headers.get(MCP_KEY_HEADER),
      workerEnv.ZAMMAD_EDGE_KEY,
    );
    if (mcpGate.kind === "unauthorized") {
      return new Response("digithings-digichat: unauthorized", { status: 401 });
    }
    if (mcpGate.kind === "not-mcp") {
      if (isContainerInternalPath(url.pathname)) {
        // Container-internal (dev-only) surface the app itself refuses in
        // production. Serving the app under /chat makes the whole /chat tree
        // reachable, so the edge refuses these too instead of relying on the
        // app's own guard alone.
        return new Response("digichat Worker: path not available.", { status: 404 });
      }
      if (!shouldProxyToDigiChat(url.pathname)) {
        return new Response(
          "digichat Worker: path not routed. The digichat app is at /chat; marketing is on Pages.",
          { status: 404 },
        );
      }
    }
    // One shared instance — digithings, OCC, and future tenants via embed registry.
    // The id is derived from the deploying commit, never hand-pinned: a warm
    // instance keeps its boot env, so a forgotten bump silently serves the old
    // image. See paths.ts. Same `containerId` the reset lever above destroys.
    const container = getContainer(workerEnv.DIGICHAT, containerId);
    // The Container slot is shared, and a rollout can leave the previous
    // instance draining while this one starts. A busy slot comes back as a
    // retryable 503 instead of a hard failure (DIG-4487).
    // A failed page/frame load is always served as inline HTML (never a
    // download on phones); API callers keep the original answer.
    //
    // The path the Container sees carries the app's base path (DIG-5121): the
    // image is built with `basePath: /chat`, so the legacy compatibility
    // routes are moved under it and the canonical /chat paths are passed
    // through unchanged.
    const containerRequest = withContainerPath(request, url.pathname);
    // DIG-3585: the OCC page's API calls. After the invite link's 302 the
    // browser holds the invite only as the occ_invite cookie, so the edge is
    // what makes a /chat/api/* call from /chat/occ an OCC call — and the only
    // thing that can: the client's own tenant headers are dropped on those
    // calls, and a house page's calls are never upgraded by the cookie.
    // Judged on the path the container sees, so a legacy /api/* alias is bound
    // the same way as its /chat/api/* target.
    if (isChatApiPath(new URL(containerRequest.url).pathname)) {
      await bindOccApiCall(
        containerRequest,
        workerEnv.OCC_INVITE_KEY,
        occCookiePolicy(workerEnv),
      );
    }
    // The invite cookie stops at the edge on every path, like the edge key.
    withoutInviteCookie(containerRequest.headers);
    // The edge key stops at the edge: the container never sees it. The header
    // is dropped from the COPY, so the original request still carries it.
    containerRequest.headers.delete(MCP_KEY_HEADER);
    return frameSafeErrorResponse(
      containerRequest,
      await fetchContainerWithRetry(containerRequest, (req) => container.fetch(req)),
    );
  },
};
