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
  SHARED_DIGICHAT_CONTAINER_ID,
  shouldProxyToDigiChat,
} from "./paths";
import { legacyEmbedEnabledValue } from "./embed-flag";

/**
 * `env` from `cloudflare:workers` is untyped until `wrangler types` generates
 * `worker-configuration.d.ts`; the local `Env` interface is the intended shape.
 */
const workerVars = env as unknown as Env;

export class DigiChatContainer extends Container {
  defaultPort = 3000;
  /** Keep warm enough for chat; tune cost vs cold-start. */
  sleepAfter = "15m";
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
      "digithings.ai,www.digithings.ai,occ.digithings.ai",
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
    DIGICHAT_DASHBOARD_SUPABASE_URL: workerVars.DIGICHAT_DASHBOARD_SUPABASE_URL ?? "",
    DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY:
      workerVars.DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY ?? "",
  };
}

export interface Env {
  DIGICHAT: DurableObjectNamespace<DigiChatContainer>;
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
  DIGICHAT_DASHBOARD_SUPABASE_URL?: string;
  DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY?: string;
}

export default {
  async fetch(request: Request, workerEnv: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!shouldProxyToDigiChat(url.pathname)) {
      return new Response(
        "digichat Worker: path not routed. Marketing /chat shells are on Pages.",
        { status: 404 },
      );
    }
    // One shared instance — digithings, OCC, and future tenants via embed registry.
    const container = getContainer(
      workerEnv.DIGICHAT,
      SHARED_DIGICHAT_CONTAINER_ID,
    );
    return container.fetch(request);
  },
};
