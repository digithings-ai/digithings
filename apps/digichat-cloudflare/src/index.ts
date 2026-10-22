/**
 * digithings digichat — Worker fronting one Cloudflare Container.
 * Proxies /embed, digichat APIs, and /_dtchat assets to the digichat Node image.
 *
 * Website paths (different chats, same Container):
 *   digithings.ai/chat      → Pages iframe → /embed?host=digithings.ai
 *   digithings.ai/chat/occ  → Pages iframe → /embed?host=occ.digithings.ai
 */
import { Container, getContainer } from "@cloudflare/containers";
import { env } from "cloudflare:workers";
import {
  DIGICHAT_CONTAINER_REV_VAR,
  digichatContainerRev,
  sharedDigichatContainerId,
  shouldProxyToDigiChat,
} from "./paths";
import { legacyEmbedEnabledValue } from "./embed-flag";
import { resolveEmbedTenants } from "./tenants-kv";
import { isOccShellPath, occGate } from "./occ-gate";
import { frameSafeErrorResponse } from "./frame-safe-error";
import { digichatContainerReset } from "./admin-reset";
import { fetchContainerWithRetry } from "./container-retry";

/**
 * `env` from `cloudflare:workers` is untyped until `wrangler types` generates
 * `worker-configuration.d.ts`; the local `Env` interface is the intended shape.
 */
const workerVars = env as unknown as Env;

/**
 * OCC helpdesk MCP: the secret-gated edge path served by the in-container
 * zammad-mcp (python) through the trusted proxy, not by Next.
 */
const ZAMMAD_MCP_PREFIX = "/api/mcp/zammad";

/**
 * Worker-owned, secret-gated recovery lever for the shared Container. Handled
 * here (never proxied to the container) so `destroy()` can reclaim an instance
 * that outlived its idle tail and still holds one of the Worker's container
 * slots (wrangler.toml allows two, so a stuck instance no longer starves
 * every cold start on its own).
 */
const DIGICHAT_ADMIN_RESET_PATH = "/_digichat-admin/container/reset";

export class DigiChatContainer extends Container {
  defaultPort = 3000;
  /** Short idle tail: each wake bills for the whole sleepAfter window. */
  sleepAfter = "1m";
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
    DIGIGRAPH_INTERNAL_URL: workerVars.DIGIGRAPH_INTERNAL_URL ?? "",
    DIGIKEY_URL: workerVars.DIGIKEY_URL ?? "",
    DIGIKEY_BFF_TOKEN: workerVars.DIGIKEY_BFF_TOKEN ?? "",
    DIGICHAT_PLAN_PROOF_SECRET: workerVars.DIGICHAT_PLAN_PROOF_SECRET ?? "",
    DIGICHAT_MONITOR_TOKENS: workerVars.DIGICHAT_MONITOR_TOKENS ?? "",
    // Trial-proof mint/verify secret (DIG-4530); must reach the container process.
    DIGICHAT_TRIAL_PROOF_SECRET: workerVars.DIGICHAT_TRIAL_PROOF_SECRET ?? "",
    // Tenant mint credentials (DIG-4530); must reach the container process.
    DIGICHAT_TENANT_MINT_CREDENTIALS: workerVars.DIGICHAT_TENANT_MINT_CREDENTIALS ?? "",
    DIGICHAT_DASHBOARD_SUPABASE_URL: workerVars.DIGICHAT_DASHBOARD_SUPABASE_URL ?? "",
    DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY:
      workerVars.DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY ?? "",
    // Read-only Zammad helpdesk MCP (in-container zammad-mcp, OCC tickets).
    ZAMMAD_API_TOKEN: workerVars.ZAMMAD_API_TOKEN ?? "",
    ZAMMAD_BASE_URL: workerVars.ZAMMAD_BASE_URL ?? "",
  };

  private tenantsResolved = false;

  /**
   * Before the container boots, build DIGICHAT_EMBED_TENANTS from the KV
   * tenant config (secret refs resolved from Worker secrets), falling back to
   * the legacy secret. See ./tenants-kv.ts. Config edits apply on next boot.
   */
  override async fetch(request: Request): Promise<Response> {
    if (!this.tenantsResolved) {
      try {
        const { json, source } = await resolveEmbedTenants(
          workerVars.DIGICHAT_TENANTS_KV,
          workerVars.DIGICHAT_EMBED_TENANTS,
          workerVars as unknown as Record<string, unknown>,
        );
        this.envVars = { ...this.envVars, DIGICHAT_EMBED_TENANTS: json };
        console.log(`[tenants-kv] embed tenants source=${source}`);
      } catch (e) {
        // A tenant-config failure must not 500 every proxied request (embed,
        // chat, assets, /healthz). Fail closed to no tenants for this boot;
        // onStop() re-arms the resolution for the next boot.
        console.error(`[tenants-kv] tenant config unavailable, serving no tenants: ${(e as Error).message}`);
        this.envVars = { ...this.envVars, DIGICHAT_EMBED_TENANTS: "" };
      }
      this.tenantsResolved = true;
    }
    return super.fetch(request);
  }

  /** Re-read KV tenant config on the next boot (the DO outlives container sleeps). */
  override onStop(): void {
    this.tenantsResolved = false;
  }
}

export interface Env {
  DIGICHAT: DurableObjectNamespace<DigiChatContainer>;
  /** DIG-1210 invite key gating the /chat/occ Pages shell. Worker-only. */
  OCC_INVITE_KEY?: string;
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
  /** KV with key `embed-tenants` (non-secret tenant config; refs via *Env). */
  DIGICHAT_TENANTS_KV?: KVNamespace;
  DIGIGRAPH_INTERNAL_URL?: string;
  DIGIKEY_URL?: string;
  DIGIKEY_BFF_TOKEN?: string;
  DIGICHAT_PLAN_PROOF_SECRET?: string;
  DIGICHAT_MONITOR_TOKENS?: string;
  /** HMAC secret backing the trial-proof mint/verify path (DIG-4530). */
  DIGICHAT_TRIAL_PROOF_SECRET?: string;
  /** Per-tenant credentials used by the mint path (DIG-4530). */
  DIGICHAT_TENANT_MINT_CREDENTIALS?: string;
  DIGICHAT_DASHBOARD_SUPABASE_URL?: string;
  DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY?: string;
  /** Read-only Zammad helpdesk MCP: base URL + API token, forwarded to the container. */
  ZAMMAD_API_TOKEN?: string;
  ZAMMAD_BASE_URL?: string;
  /** Worker-only gate for /api/mcp/zammad*; never forwarded to the container. */
  ZAMMAD_EDGE_KEY?: string;
  /**
   * Worker-only key for the container reset lever; never forwarded to the
   * container. Unset means the lever is off (the route answers 404).
   */
  DIGICHAT_ADMIN_KEY?: string;
}

export default {
  async fetch(request: Request, workerEnv: Env): Promise<Response> {
    const url = new URL(request.url);
    if (isOccShellPath(url.pathname)) {
      return occGate(request, workerEnv.OCC_INVITE_KEY);
    }
    // Worker-owned reset lever: intercepted here, before any container proxy,
    // and fail-closed with a 404 that never discloses the route. The instance
    // it destroys is the same derived id the proxy below addresses, computed
    // once here from the deploy's rev.
    const containerId = sharedDigichatContainerId(workerEnv.DIGICHAT_CONTAINER_REV);
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
    const isZammadMcp = url.pathname.startsWith(ZAMMAD_MCP_PREFIX);
    if (isZammadMcp) {
      const expected = workerEnv.ZAMMAD_EDGE_KEY?.trim();
      const provided = request.headers.get("x-digi-mcp-key")?.trim();
      if (!expected || !provided || provided !== expected) {
        return new Response("digithings-digichat: unauthorized", { status: 401 });
      }
    } else if (!shouldProxyToDigiChat(url.pathname)) {
      return new Response(
        "digichat Worker: path not routed. Marketing /chat shells are on Pages.",
        { status: 404 },
      );
    }
    // One shared instance — digithings, OCC, and future tenants via embed registry.
    // The id is derived from the deploying commit, never hand-pinned: a warm
    // instance keeps its boot env, so a forgotten bump silently serves the old
    // image. See paths.ts. Same `containerId` the reset lever above destroys.
    const container = getContainer(workerEnv.DIGICHAT, containerId);
    // The container slot is shared, and a rollout can leave the previous
    // instance draining while this one starts. A busy slot comes back as a
    // retryable 503 instead of a hard failure (DIG-4487).
    // A failed page/frame load is always served as inline HTML (never a
    // download on phones); API callers keep the original answer.
    return frameSafeErrorResponse(
      request,
      await fetchContainerWithRetry(request, (req) => container.fetch(req)),
    );
  },
};
