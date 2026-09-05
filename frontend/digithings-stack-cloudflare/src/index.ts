/**
 * digithings Profile A stack — Worker fronting one Cloudflare Container.
 *
 * Hostnames:
 *   graph.digithings.ai → digigraph :8000
 *   key.digithings.ai   → digikey   :8005
 *
 * workers.dev fallbacks:
 *   /healthz            → digigraph
 *   /_stack/key/*       → digikey (strip prefix)
 *
 * digisearch / digivault / LiteLLM are loopback-only inside the Container.
 * digichat Container calls these public URLs via DIGIGRAPH_INTERNAL_URL / DIGIKEY_URL.
 */
import { Container, getContainer, switchPort } from "@cloudflare/containers";
import { env as workerEnvBinding } from "cloudflare:workers";
import {
  DIGIGRAPH_PORT,
  DIGIKEY_PORT,
  SHARED_STACK_CONTAINER_ID,
  portForHostname,
} from "./ports";

/** Wrangler injects vars/secrets; cast until `wrangler types` is generated in CI. */
const env = workerEnvBinding as unknown as Env;

export class DigiStackContainer extends Container {
  defaultPort = DIGIGRAPH_PORT;
  /**
   * digigraph is required for Worker readiness. digikey is also waited on in
   * fetch() once Redis-wait + early priority make bind reliable under Firecracker.
   */
  requiredPorts = [DIGIGRAPH_PORT];
  /** Keep warm — multi-process cold start is expensive. */
  sleepAfter = "2h";

  /**
   * Runtime env for supervisord processes. Secrets from `wrangler secret put`;
   * plain vars from wrangler.toml `[vars]`.
   */
  envVars = {
    DIGIKEY_ISSUER: env.DIGIKEY_ISSUER ?? "https://key.digithings.ai",
    DIGIKEY_AUDIENCE: env.DIGIKEY_AUDIENCE ?? "digi-ecosystem",
    // Default deny — local compose sets ALLOW=1; CF wrangler.toml [vars] sets "0".
    DIGIKEY_ALLOW_EPHEMERAL_KEY: env.DIGIKEY_ALLOW_EPHEMERAL_KEY ?? "0",
    DIGIKEY_ALLOW_DEV_GLOBAL: env.DIGIKEY_ALLOW_DEV_GLOBAL ?? "0",
    DIGIKEY_BFF_TOKEN: env.DIGIKEY_BFF_TOKEN ?? "",
    DIGIKEY_PRIVATE_KEY_PEM: env.DIGIKEY_PRIVATE_KEY_PEM ?? "",
    DIGIKEY_ADMIN_TOKEN: env.DIGIKEY_ADMIN_TOKEN ?? "",
    DIGIKEY_DATABASE_URL:
      env.DIGIKEY_DATABASE_URL ?? "sqlite:////data/digikey.db",
    DIGIKEY_JWKS_URL: "http://127.0.0.1:8005/.well-known/jwks.json",
    DIGIVAULT_URL: env.DIGIVAULT_URL ?? "http://127.0.0.1:8004",
    DIGISEARCH_URL: env.DIGISEARCH_URL ?? "http://127.0.0.1:8002",
    DIGIQUANT_URL: env.DIGIQUANT_URL ?? "",
    DIGISMITH_URL: env.DIGISMITH_URL ?? "",
    OPENAI_API_BASE: env.OPENAI_API_BASE ?? "http://127.0.0.1:4000/v1",
    DIGI_LLM_MODE: env.DIGI_LLM_MODE ?? "test",
    CHROMA_PATH: env.CHROMA_PATH ?? "/data/chroma",
    // Canonical shared Cloudflare credential pair (#2239 rename) -- one account +
    // token now authorizes both Vectorize and D1. VECTORIZE_*/D1_ACCOUNT_ID/
    // D1_API_TOKEN below are the legacy names: still forwarded, still live Worker
    // secrets, and still read as a fallback by the container's Python side
    // (digivault.server / digisearch.search._stub's _first_env-style lookups), so
    // this rename ships with zero downtime -- delete the legacy secrets only once
    // CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN are set and verified working.
    CLOUDFLARE_ACCOUNT_ID: env.CLOUDFLARE_ACCOUNT_ID ?? "",
    CLOUDFLARE_API_TOKEN: env.CLOUDFLARE_API_TOKEN ?? "",
    VECTORIZE_ACCOUNT_ID: env.VECTORIZE_ACCOUNT_ID ?? "",
    VECTORIZE_API_TOKEN: env.VECTORIZE_API_TOKEN ?? "",
    D1_ACCOUNT_ID: env.D1_ACCOUNT_ID ?? "",
    D1_API_TOKEN: env.D1_API_TOKEN ?? "",
    D1_DATABASE_MAP: env.D1_DATABASE_MAP ?? "",
    DIGIVAULT_ROOT: env.DIGIVAULT_ROOT ?? "/data/vault",
    DIGISEARCH_INDEX: env.DIGISEARCH_INDEX ?? "digithings_docs",
    DIGI_TENANT_CORPUS_MAP:
      env.DIGI_TENANT_CORPUS_MAP ??
      '{"digithings":{"digisearchIndex":"digithings_docs","vaultPathPrefix":"clients/digithings"},"occ":{"digisearchIndex":"occ_help","vaultPathPrefix":"clients/online-compliance-center"}}',
    GROQ_API_KEY: env.GROQ_API_KEY ?? "",
    OPENROUTER_API_KEY: env.OPENROUTER_API_KEY ?? "",
    OPENAI_API_KEY: env.OPENAI_API_KEY ?? "",
    // Hosted Cheaper Inference (house default when key set; see docs/providers/cheaperinference.md)
    CHEAPERINFERENCE_API_KEY: env.CHEAPERINFERENCE_API_KEY ?? "",
    CHEAPERINFERENCE_API_BASE:
      env.CHEAPERINFERENCE_API_BASE ?? "https://api.cheaperinference.com/v1",
    DIGI_HOUSE_UPSTREAM: env.DIGI_HOUSE_UPSTREAM ?? "",
    LITELLM_PROXY_API_KEY: env.LITELLM_PROXY_API_KEY ?? "",
    LITELLM_MASTER_KEY: env.LITELLM_MASTER_KEY ?? "",
  };

  /**
   * Wait longer than the default ~20s portReadyTimeout while supervisord
   * brings up digigraph (and digikey) under Firecracker.
   */
  override async fetch(request: Request): Promise<Response> {
    // switchPort sets cf-container-target-port; containerFetch(request) alone
    // ignores that header and always uses defaultPort (digigraph :8000) — which
    // made key.digithings.ai / JWKS / bff_session hit digigraph (smoke NO-GO).
    const targetPort = targetPortFromRequest(request);
    try {
      await this.startAndWaitForPorts({
        ports: [DIGIGRAPH_PORT, ...(targetPort === DIGIKEY_PORT ? [DIGIKEY_PORT] : [])],
        cancellationOptions: {
          portReadyTimeoutMS: 180_000,
          instanceGetTimeoutMS: 60_000,
        },
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return new Response(`stack container not ready: ${message}`, {
        status: 503,
      });
    }
    return this.containerFetch(request, targetPort);
  }
}

function targetPortFromRequest(request: Request): number {
  const header = request.headers.get("cf-container-target-port");
  if (header) {
    const parsed = Number.parseInt(header, 10);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return DIGIGRAPH_PORT;
}

export interface Env {
  STACK: DurableObjectNamespace<DigiStackContainer>;
  DIGIKEY_ISSUER?: string;
  DIGIKEY_AUDIENCE?: string;
  DIGIKEY_ALLOW_EPHEMERAL_KEY?: string;
  DIGIKEY_ALLOW_DEV_GLOBAL?: string;
  DIGIKEY_BFF_TOKEN?: string;
  DIGIKEY_PRIVATE_KEY_PEM?: string;
  DIGIKEY_ADMIN_TOKEN?: string;
  DIGIKEY_DATABASE_URL?: string;
  DIGIVAULT_URL?: string;
  DIGISEARCH_URL?: string;
  DIGIQUANT_URL?: string;
  DIGISMITH_URL?: string;
  OPENAI_API_BASE?: string;
  DIGI_LLM_MODE?: string;
  CHROMA_PATH?: string;
  CLOUDFLARE_ACCOUNT_ID?: string;
  CLOUDFLARE_API_TOKEN?: string;
  VECTORIZE_ACCOUNT_ID?: string;
  VECTORIZE_API_TOKEN?: string;
  D1_ACCOUNT_ID?: string;
  D1_API_TOKEN?: string;
  D1_DATABASE_MAP?: string;
  DIGIVAULT_ROOT?: string;
  DIGISEARCH_INDEX?: string;
  DIGI_TENANT_CORPUS_MAP?: string;
  GROQ_API_KEY?: string;
  OPENROUTER_API_KEY?: string;
  OPENAI_API_KEY?: string;
  CHEAPERINFERENCE_API_KEY?: string;
  CHEAPERINFERENCE_API_BASE?: string;
  DIGI_HOUSE_UPSTREAM?: string;
  LITELLM_PROXY_API_KEY?: string;
  LITELLM_MASTER_KEY?: string;
}

function rewriteKeyStackPath(request: Request): Request {
  const url = new URL(request.url);
  const stripped = url.pathname.replace(/^\/_stack\/key/, "") || "/";
  url.pathname = stripped;
  return new Request(url.toString(), request);
}

export default {
  async fetch(request: Request, workerEnv: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/_stack/meta") {
      return Response.json({
        ok: true,
        service: "digithings-stack",
        containerId: SHARED_STACK_CONTAINER_ID,
        note: "Worker up; container ports may still be starting",
      });
    }

    // workers.dev digikey probe without custom domain: /_stack/key/healthz
    if (url.pathname === "/_stack/key" || url.pathname.startsWith("/_stack/key/")) {
      const container = getContainer(workerEnv.STACK, SHARED_STACK_CONTAINER_ID);
      return container.fetch(switchPort(rewriteKeyStackPath(request), DIGIKEY_PORT));
    }

    const port = portForHostname(url.hostname);
    if (port === null) {
      return new Response(
        "digithings-stack: unknown host. Use graph.digithings.ai, key.digithings.ai, or /_stack/key/* on workers.dev.",
        { status: 404 },
      );
    }
    const container = getContainer(workerEnv.STACK, SHARED_STACK_CONTAINER_ID);
    return container.fetch(switchPort(request, port));
  },
};
