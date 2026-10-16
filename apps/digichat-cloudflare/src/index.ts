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
import { isOccShellPath, occGate } from "./occ-gate";

/**
 * `env` from `cloudflare:workers` is untyped until `wrangler types` generates
 * `worker-configuration.d.ts`; the local `Env` interface is the intended shape.
 */
const workerVars = env as unknown as Env;

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
    DIGICHAT_DASHBOARD_SUPABASE_URL: workerVars.DIGICHAT_DASHBOARD_SUPABASE_URL ?? "",
    DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY:
      workerVars.DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY ?? "",
  };
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
  DIGIGRAPH_INTERNAL_URL?: string;
  DIGIKEY_URL?: string;
  DIGIKEY_BFF_TOKEN?: string;
  DIGICHAT_PLAN_PROOF_SECRET?: string;
  DIGICHAT_MONITOR_TOKENS?: string;
  DIGICHAT_DASHBOARD_SUPABASE_URL?: string;
  DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY?: string;
}

export default {
  async fetch(request: Request, workerEnv: Env): Promise<Response> {
    const url = new URL(request.url);
    if (isOccShellPath(url.pathname)) {
      return occGate(request, workerEnv.OCC_INVITE_KEY);
    // Served by the Worker itself, never proxied: the id a deploy derived is
    // the only thing that makes a deploy verifiable rather than assumed, and
    // `/api/health` + `/healthz` are both digichat paths (proxied into the
    // container), so the Worker could not answer them.
    if (url.pathname === "/_digichat/meta") {
      return Response.json({
        ok: true,
        service: "digichat",
        containerId: sharedDigichatContainerId(workerEnv.DIGICHAT_CONTAINER_REV),
        rev: digichatContainerRev(workerEnv.DIGICHAT_CONTAINER_REV),
        revVar: DIGICHAT_CONTAINER_REV_VAR,
        note:
          "Worker up; the container may still be starting. rev: null means " +
          "this deploy carried no " +
          DIGICHAT_CONTAINER_REV_VAR +
          " and fell back to the legacy id.",
      });
    }
    if (!shouldProxyToDigiChat(url.pathname)) {
      return new Response(
        "digichat Worker: path not routed. Marketing /chat shells are on Pages.",
        { status: 404 },
      );
    }
    // One shared instance — digithings, OCC, and future tenants via embed registry.
    // The id is derived from the deploying commit, never hand-pinned: a warm
    // instance keeps its boot env, so a forgotten bump silently serves the old
    // image. See paths.ts.
    const container = getContainer(
      workerEnv.DIGICHAT,
      sharedDigichatContainerId(workerEnv.DIGICHAT_CONTAINER_REV),
    );
    return container.fetch(request);
  },
};
