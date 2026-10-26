/**
 * digithings Profile A stack — Worker fronting one Cloudflare Container.
 *
 * Hostnames:
 *   graph.digithings.ai  → digigraph  :8000
 *   key.digithings.ai    → digikey    :8005
 *   search.digithings.ai → digisearch :8002 (digikey JWT `digisearch:query`;
 *                          new external route #4063, owner-approved)
 *   mcp.digithings.ai    → digiquant-mcp :8767 (reserved; see HUMAN GATE in
 *                          wrangler.toml — route enabled only with edge auth)
 *
 * workers.dev fallbacks:
 *   /healthz            → digigraph
 *   /_stack/key/*       → digikey (strip prefix)
 *
 * /_stack/mcp/{digisearch,digivault}/* → in-container MCP servers on
 * :8765/:8769. Two credentials are accepted, either one grants: a digikey JWT
 * in `Authorization: Bearer` carrying `mcp:digisearch` / `mcp:digivault`
 * (verified against DIGIKEY_JWKS_URL), or the static `x-digi-mcp-key` header
 * matching MCP_EDGE_KEY / MCP_EDGE_KEYS (compose and self-host, where no
 * digikey mints a token). Fail-closed 401 otherwise, 403 for a valid token
 * without the server's scope. See ./mcp-edge-auth.
 * mcp.digithings.ai stays reserved and answers only behind its JWT gate.)
 *
 * /dashboard-api/* → folded dashboard-api routes (#4687: portfolio,
 * allocations, brief, performance, kpis/live, nav-series, benchmarks, ledger,
 * /v1/tables/*, POST /mcp with the 8 dashboard MCP tools) served in-worker
 * behind the dashboard-api isolation group. The standalone dashboard-api
 * worker stays deployed until cutover; no DNS/Pages changes in this slice.
 *
 * digichat is NOT served here: the #4689 fold was dropped (Chris, 2026-10-19)
 * and the product (plus OCC, one of its tenants) runs only in
 * apps/digichat-cloudflare on the `digithings-digichat` Worker's own Container.
 *
 * digisearch-mcp / digivault-mcp bind 0.0.0.0 inside the Container
 * for those edge routes; LiteLLM stays loopback-only. digisearch also binds
 * 0.0.0.0:8002 (container/start_digisearch.sh) so the Worker can reach it at the
 * container network address for its public route; in-container callers keep
 * using DIGISEARCH_URL=http://127.0.0.1:8002 (0.0.0.0 includes loopback).
 */
import { Container, getContainer, switchPort } from "@cloudflare/containers";
import { env as workerEnvBinding } from "cloudflare:workers";
import {
  CONTAINER_RETRY_AFTER_SECONDS,
  classifyContainerHopFailure,
  containerEvictedResponse,
  containerFailedResponse,
  containerRestartMessage,
  containerUnavailableResponse,
  isContainerEvictedError,
  isContainerFailedError,
  safeErrorMessage,
} from "./container-errors";
import { fetchWithContainerRetry } from "./container-retry";
import { authorizeMcpEdge } from "./mcp-edge-auth";
import { getStackStatus, runIsolated } from "./route-modules";
import { SESSION_MODEL_ALLOWLIST_DEFAULT } from "./session-model-allowlist";
import { composeCorpusMap } from "./tenant-config";
// ports.ts stays a static import: the two Container subclasses below need
// their ports synchronously at instantiation (class fields cannot await), and
// the file is dependency-free constants, so it cannot fail independently of
// the worker bundle. Every fetch() route group additionally lazy-loads it
// through runIsolated (per-group import() + try/catch, #4685), so a future
// load failure degrades only its own paths.
import {
  DIGIGRAPH_PORT,
  DIGIKEY_PORT,
  DIGISEARCH_PORT,
  DIGIQUANT_MCP_HOSTNAME,
  DIGIQUANT_MCP_PORT,
  MCP_CONTAINER_ID,
  portForHostname,
  sharedStackContainerId,
  stackContainerRev,
} from "./ports";
import {
  digichatContainerRev,
  sharedDigichatContainerId,
} from "./digichat";
import {
  containerIsAwake,
  isHealthProbe,
  isScannerPath,
  scannerResponse,
  sleepingHealthResponse,
} from "./wake-hygiene";

/** Wrangler injects vars/secrets; cast until `wrangler types` is generated in CI. */
const env = workerEnvBinding as unknown as Env;

export class DigiStackContainer extends Container {
  defaultPort = DIGIGRAPH_PORT;
  /**
   * digigraph is required for Worker readiness. digikey and digisearch are waited
   * on per-request in fetch() instead: digisearch starts behind the Chroma seed
   * wait, and digikey is a hard dependency of every authenticated route (it serves
   * the JWKS the verifiers fetch), so it can never be optional.
   */
  requiredPorts = [DIGIGRAPH_PORT];
  /**
   * Cold starts are seamless (#4323), but the idle timer also runs while
   * supervisord is still booting: at 1m a slow cold boot (digigraph + digikey
   * well past 60s) was stopped mid-boot by "Activity expired" and never bound
   * its ports (OCC outage 2026-10-14). 5m covers the 180s port wait.
   */
  sleepAfter = "5m";

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
    // No SQLite fallback: the Container's /data is ephemeral, so a synthesized
    // default would silently lose every issued key. Unset means digikey refuses
    // to start (#4080).
    DIGIKEY_DATABASE_URL: env.DIGIKEY_DATABASE_URL ?? "",
    DIGIKEY_JWKS_URL: "http://127.0.0.1:8005/.well-known/jwks.json",
    DIGIVAULT_URL: env.DIGIVAULT_URL ?? "http://127.0.0.1:8004",
    DIGISEARCH_URL: env.DIGISEARCH_URL ?? "http://127.0.0.1:8002",
    DIGIQUANT_URL: env.DIGIQUANT_URL ?? "",
    DIGITRACE_URL: env.DIGITRACE_URL ?? "",
    OPENAI_API_BASE: env.OPENAI_API_BASE ?? "http://127.0.0.1:4000/v1",
    DIGI_LLM_MODE: env.DIGI_LLM_MODE ?? "test",
    // Session model picker (OCC settings): house-upstream slugs a visitor may
    // pick per session. digigraph binds only slugs on this list. Set in
    // wrangler.toml [vars] when present, and config wins; the code fallback is
    // derived from the set the deployment publishes, so it can never drift
    // from it — see ./session-model-allowlist and check_model_name_literals.
    DIGI_SESSION_MODEL_ALLOWLIST:
      env.DIGI_SESSION_MODEL_ALLOWLIST ?? SESSION_MODEL_ALLOWLIST_DEFAULT,
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
    // All indexes (docs + tickets, all tenants) embed with this model id (#4756).
    // Same 384 dims across models: a mismatch retrieves silently wrong results,
    // so ingest, backfill, and query must agree on exactly this value.
    DIGISEARCH_EMBEDDING_PROVIDER:
      env.DIGISEARCH_EMBEDDING_PROVIDER ?? "Xenova/paraphrase-multilingual-MiniLM-L12-v2",
    // Per-index bge-m3 override (DIG-4657): the indexes listed here are queried
    // with Cloudflare Workers AI @cf/baai/bge-m3 (1024 dims) instead of the
    // global 384-dim provider above. The corpus-index worker writes those
    // indexes with bge-m3, so the query side must use the same model or the
    // query vector does not match the stored vectors and retrieval silently
    // misses. Digisearch reads the list per query (search/_stub.py).
    DIGISEARCH_WORKERS_AI_INDEXES: env.DIGISEARCH_WORKERS_AI_INDEXES ?? "",
    // Cloudflare caps a text binding at 5.1 kB and the whole map was 5285 bytes,
    // so `wrangler deploy` failed with code 10054 and wrangler.toml now ships it
    // as two vars. This joins them; ./tenant-config owns the merge rule (primary
    // wins on a slug collision, digithings-only floor when neither half is
    // usable). The composed string is byte-identical to the old single var.
    DIGI_TENANT_CORPUS_MAP: composeCorpusMap(
      env.DIGI_TENANT_CORPUS_MAP,
      env.DIGI_TENANT_CORPUS_MAP_EXTRA,
    ),
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
   * A request waiting on a cold start must not have the container stopped under
   * it. `startAndWaitForPorts` does NOT renew the activity timer, so with
   * sleepAfter = "5m" the idle alarm fires mid-boot and SIGTERMs the container
   * before its port opens; the port wait then fails with "The container is not
   * running, consider calling start()" and every caller gets 503
   * container_booting while the container itself logs a clean boot (no errors,
   * every supervisord program RUNNING). Observed 2026-10-18 with the previous
   * 1m window: after the R5 wheel install (#5762) the boot takes ~60s at 0.5
   * vCPU, which is exactly that window. Holding the window open for the life of
   * the request is the fix; the idle tail itself is unchanged once requests
   * stop.
   */
  private keepAwakeForRequest = false;

  /** Sleep only when nothing is waiting on us (see keepAwakeForRequest). */
  override async onActivityExpired(): Promise<void> {
    if (this.keepAwakeForRequest) return;
    await super.onActivityExpired();
  }

  /**
   * Wait longer than the default ~20s portReadyTimeout while supervisord
   * brings up digigraph (and the requested service) under Firecracker.
   */
  override async fetch(request: Request): Promise<Response> {
    // Hold the idle window open for as long as this request is waiting on a
    // cold start (see keepAwakeForRequest).
    this.keepAwakeForRequest = true;
    // switchPort sets cf-container-target-port; containerFetch(request) alone
    // ignores that header and always uses defaultPort (digigraph :8000) — which
    // made key.digithings.ai / JWKS / bff_session hit digigraph (smoke NO-GO).
    const targetPort = targetPortFromRequest(request);
    try {
      await this.startAndWaitForPorts({
        // digigraph binds first for every request, so it is unconditional.
        // digisearch starts behind the Chroma seed wait, so it is waited on only
        // for its own route.
        // digikey is unconditional: digisearch verifies the digikey JWT against
        // the :8005 JWKS on every authenticated call, so proxying a search request
        // before :8005 binds is a cold-wake 401 invalid_token (and a 503 once the
        // blocklist check runs). This gates every route, including the auth-exempt
        // ones (/healthz, the /_stack/mcp/* proxies) — intentional: an unready
        // digikey is the failure we are fixing, not a distinct case worth a second
        // code path. digikey waits up to 30s for redis before binding
        // (container/start_digikey.sh; it binds anyway after the wait), so in
        // practice this also covers the blocklist 503 window — redis is a
        // supervisord priority-10 program, so it is up first. See #4546.
        ports: [
          DIGIGRAPH_PORT,
          DIGIKEY_PORT,
          ...(targetPort === DIGISEARCH_PORT ? [DIGISEARCH_PORT] : []),
        ],
        cancellationOptions: {
          portReadyTimeoutMS: 180_000,
          instanceGetTimeoutMS: 60_000,
        },
      });
    } catch (err) {
      const message = safeErrorMessage(err);
      // DIG-3226: a confirmed eviction is not a cold start — return the
      // non-retryable 410 so callers stop retrying a container that is gone
      // (same distinction as digiquant-runner RunLostError, runner.ts).
      if (isContainerEvictedError(message)) {
        return containerEvictedResponse("stack", message);
      }
      // DIG-4477: the container was RECYCLED or FAILED under the request (a
      // rollout exit, an unexpected exit, "no container instance"). That is not
      // a cold boot: a fresh instance can serve the request, so answer with
      // the retryable `container_failed` code and let the Worker retry once
      // instead of surfacing the failure to the client. The matched shapes are
      // the @cloudflare/containers producer constants listed in
      // ./container-errors.ts; this Worker's documented cold-boot kill
      // (index.ts #5762) is deliberately NOT one of them and keeps 503
      // `container_booting`.
      if (isContainerFailedError(message)) {
        return containerFailedResponse("stack", message);
      }
      return containerBootingResponse("stack", message);
    } finally {
      this.keepAwakeForRequest = false;
    }
    // An eviction can also land between start and fetch: map the confirmed
    // signals (evicted -> 410, failed -> retryable 503) and rethrow
    // everything else so the existing failure behavior is unchanged.
    let response: Response;
    try {
      response = await this.containerFetch(request, targetPort);
    } catch (err) {
      // A hop that rejected with a value that is not an Error (DIG-4928): the
      // @cloudflare/containers package rethrows such a value verbatim from its
      // proxy catch, so it would leave this Durable Object as an uncaught
      // exception and the platform would record it as it stands — a thrown
      // Date leaves nothing but a bare date in the log.
      //
      // Such a value states no failure of its own, so it is neither an
      // eviction nor a failed container: it cannot be classified, and it is
      // not replayed either (a value that came out of the hop says nothing
      // about whether the request reached the container). The client is told
      // to come back instead.
      //
      // The classification is decided in ONE place (classifyContainerHopFailure),
      // so the order of the checks cannot drift between the two container
      // classes: a value that is not an Error is read before the eviction and
      // the failed vocabulary, whatever its text says.
      const failure = classifyContainerHopFailure(err);
      if (failure.kind === "unavailable") {
        console.error(
          "digithings-stack: container could not be reached: the container hop rejected with a value that is not an Error:",
          failure.description,
        );
        return containerUnavailableResponse("stack");
      }
      if (failure.kind === "evicted") {
        return containerEvictedResponse("stack", failure.message);
      }
      if (failure.kind === "failed") {
        return containerFailedResponse("stack", failure.message);
      }
      throw err;
    }
    // @cloudflare/containers catches a container that died mid-request ITSELF
    // and answers with a 500 instead of throwing (its own comment on that
    // branch: "This error means that the container might've just restarted"),
    // so the recycle has to be recognised on the RESPONSE. Convert it into
    // the machine-readable failed-container code so the Worker retries it
    // once (see ./container-retry.ts) instead of surfacing a bare 500.
    const restart = await containerRestartMessage(response);
    if (restart !== null) {
      return containerFailedResponse("stack", restart);
    }
    return response;
  }
}

/**
 * Dedicated digiquant-mcp market-data container (#3780 Task 8).
 *
 * Separate image (digiquant/Dockerfile.mcp: [research]+[mcp] extras,
 * streamable-http :8767) — NOT part of the Profile A stack container above
 * (Option B rejected: it would bloat the chat-only profile and couple deploys).
 * Single pinned instance (MCP_CONTAINER_ID, max_instances = 1 in
 * wrangler.toml): the MCP read path assumes a single replica (in-memory 900s
 * TTL keyed by as_of + manifest version).
 */
export class DigiQuantMcpContainer extends Container {
  defaultPort = DIGIQUANT_MCP_PORT;
  requiredPorts = [DIGIQUANT_MCP_PORT];
  /**
   * Cold-start policy: a cold start pays only the FastMCP import, never a data
   * load (R2 is the cache), so the container may sleep freely; a 1-minute idle
   * tail keeps the billed wake window minimal.
   */
  sleepAfter = "1m";

  /**
   * Runtime env for the MCP process. Secrets from `wrangler secret put`.
   * Pass-through, no silent default flip: unset/empty keeps the library
   * default (`supabase`); operators set this to "r2" explicitly via env.
   * Scope is the one deliberate hosted default: the container runs `read`
   * ONLY (`full` never leaves localhost); local runs keep defaulting to
   * `full` in `digiquant/mcp_server.py`.
   */
  envVars = {
    DIGIQUANT_MCP_SCOPE: env.DIGIQUANT_MCP_SCOPE ?? "read",
    DIGIQUANT_MARKET_DATA_BACKEND: env.DIGIQUANT_MARKET_DATA_BACKEND ?? "",
    GLOOMBERB_SESSION_COOKIE: env.GLOOMBERB_SESSION_COOKIE ?? "",
    R2_ACCOUNT_ID: env.R2_ACCOUNT_ID ?? "",
    R2_BUCKET: env.R2_BUCKET ?? "",
    R2_ACCESS_KEY_ID: env.R2_ACCESS_KEY_ID ?? "",
    R2_SECRET_ACCESS_KEY: env.R2_SECRET_ACCESS_KEY ?? "",
  };

  /**
   * Do not let the idle alarm stop a container a request is waiting on — see
   * the DigiStackContainer note: nothing renews the activity timer during
   * `startAndWaitForPorts`, so a cold start longer than sleepAfter is killed
   * mid-boot.
   */
  private keepAwakeForRequest = false;

  override async onActivityExpired(): Promise<void> {
    if (this.keepAwakeForRequest) return;
    await super.onActivityExpired();
  }

  override async fetch(request: Request): Promise<Response> {
    this.keepAwakeForRequest = true;
    try {
      await this.startAndWaitForPorts({
        ports: [DIGIQUANT_MCP_PORT],
        cancellationOptions: {
          portReadyTimeoutMS: 180_000,
          instanceGetTimeoutMS: 60_000,
        },
      });
    } catch (err) {
      const message = safeErrorMessage(err);
      // DIG-3226: confirmed eviction -> non-retryable 410, not boot 503.
      if (isContainerEvictedError(message)) {
        return containerEvictedResponse("mcp", message);
      }
      // DIG-4477: recycled / failed container -> retryable 503, one fresh
      // attempt from the Worker (see ./container-retry.ts).
      if (isContainerFailedError(message)) {
        return containerFailedResponse("mcp", message);
      }
      return containerBootingResponse("mcp", message);
    } finally {
      this.keepAwakeForRequest = false;
    }
    let response: Response;
    try {
      response = await this.containerFetch(request, DIGIQUANT_MCP_PORT);
    } catch (err) {
      // A hop that rejected with a value that is not an Error (DIG-4928): the
      // @cloudflare/containers package rethrows such a value verbatim from its
      // proxy catch, so it would leave this Durable Object as an uncaught
      // exception and the platform would record it as it stands — a thrown
      // Date leaves nothing but a bare date in the log.
      //
      // Such a value states no failure of its own, so it is neither an
      // eviction nor a failed container: it cannot be classified, and it is
      // not replayed either (a value that came out of the hop says nothing
      // about whether the request reached the container). The client is told
      // to come back instead.
      //
      // The classification is decided in ONE place (classifyContainerHopFailure),
      // so the order of the checks cannot drift between the two container
      // classes: a value that is not an Error is read before the eviction and
      // the failed vocabulary, whatever its text says.
      const failure = classifyContainerHopFailure(err);
      if (failure.kind === "unavailable") {
        console.error(
          "digithings-stack: container could not be reached: the container hop rejected with a value that is not an Error:",
          failure.description,
        );
        return containerUnavailableResponse("mcp");
      }
      if (failure.kind === "evicted") {
        return containerEvictedResponse("mcp", failure.message);
      }
      if (failure.kind === "failed") {
        return containerFailedResponse("mcp", failure.message);
      }
      throw err;
    }
    // A container that died mid-request answers with a 500, not a throw —
    // see the DigiStackContainer note and ./container-errors.ts.
    const restart = await containerRestartMessage(response);
    if (restart !== null) {
      return containerFailedResponse("mcp", restart);
    }
    return response;
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

/**
 * Machine-readable boot code for container-not-ready 503s (#4753).
 *
 * The digichat BFF keys its extended cold-boot retry budget off this code:
 * only a 503 carrying `container_booting` (plus `Retry-After`) gets the ~250s
 * budget; every other 503 keeps the 15s budget. Never reuse this code for a
 * real outage — the BFF would wait out the budget instead of failing fast.
 */
export const CONTAINER_BOOTING_CODE = "container_booting";

/**
 * JSON 503 with the boot code + Retry-After for all three containers.
 *
 * The poll hint itself lives in ./container-errors.ts
 * (CONTAINER_RETRY_AFTER_SECONDS) so the boot 503 and the failed-container
 * 503 cannot drift apart.
 */
export function containerBootingResponse(
  service: "stack" | "mcp" | "digichat",
  message: string,
): Response {
  return Response.json(
    { code: CONTAINER_BOOTING_CODE, message: `${service} container not ready: ${message}` },
    {
      status: 503,
      headers: { "Retry-After": String(CONTAINER_RETRY_AFTER_SECONDS) },
    },
  );
}

export interface Env {
  STACK: DurableObjectNamespace<DigiStackContainer>;
  MCP_STACK: DurableObjectNamespace<DigiQuantMcpContainer>;
  /**
   * Service binding to this same Worker, used only for the digikey JWKS:
   * `key.digithings.ai` is this Worker's own route, so a plain fetch cannot
   * reach it from inside (see mcp-edge-auth).
   */
  DIGIKEY_SELF?: { fetch(input: string, init?: RequestInit): Promise<Response> };
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
  DIGITRACE_URL?: string;
  /**
   * Deploying commit, injected by `scripts/deploy.mjs` at deploy time; the
   * shared-stack Container id is derived from it (ports.ts, DIG-3229). NOT in
   * wrangler.toml [vars] on purpose — unset means "this deploy carried no rev",
   * and the id falls back to the pinned legacy value. Never hand-write it.
   */
  STACK_CONTAINER_REV?: string;
  OPENAI_API_BASE?: string;
  DIGI_LLM_MODE?: string;
  /** House-upstream model slugs a visitor may pick per session (OCC picker). */
  DIGI_SESSION_MODEL_ALLOWLIST?: string;
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
  DIGISEARCH_EMBEDDING_PROVIDER?: string;
  /**
   * Comma-separated index names queried with Workers AI bge-m3 (1024 dims)
   * instead of the global provider. Shipped in wrangler.toml [vars]; the
   * corpus-index worker writes those indexes with bge-m3 (DIG-4657).
   */
  DIGISEARCH_WORKERS_AI_INDEXES?: string;
  DIGI_TENANT_CORPUS_MAP?: string;
  /**
   * Second half of the split corpus map (see `composeCorpusMap`): every tenant
   * except the house `digithings` entry. Worker-scoped -- it is read to build
   * the container's `DIGI_TENANT_CORPUS_MAP` and never forwarded itself.
   */
  DIGI_TENANT_CORPUS_MAP_EXTRA?: string;
  GROQ_API_KEY?: string;
  OPENROUTER_API_KEY?: string;
  OPENAI_API_KEY?: string;
  CHEAPERINFERENCE_API_KEY?: string;
  CHEAPERINFERENCE_API_BASE?: string;
  DIGI_HOUSE_UPSTREAM?: string;
  LITELLM_PROXY_API_KEY?: string;
  LITELLM_MASTER_KEY?: string;
  MCP_EDGE_KEY?: string;
  /** Optional per-server edge keys (`{"digivault":"…"}`); falls back to MCP_EDGE_KEY. */
  MCP_EDGE_KEYS?: string;
  /**
   * digikey JWKS endpoint the MCP edge verifies `Authorization: Bearer` JWTs
   * against (./mcp-edge-auth). Worker-scoped: the Container's copy of this name
   * is the loopback URL in `envVars` below, which the Worker cannot reach.
   * Unset means the JWT path cannot verify and refuses; the static edge key is
   * unaffected. Public URL, not a secret — it ships in wrangler.toml `[vars]`.
   */
  DIGIKEY_JWKS_URL?: string;
  DIGIQUANT_MCP_SCOPE?: string;
  DIGIQUANT_MARKET_DATA_BACKEND?: string;
  GLOOMBERB_SESSION_COOKIE?: string;
  R2_ACCOUNT_ID?: string;
  R2_BUCKET?: string;
  R2_ACCESS_KEY_ID?: string;
  R2_SECRET_ACCESS_KEY?: string;
  // Read-only market data (#4013 Task 8). Both are consumed by the Worker's
  // /v1/market/* handler (src/market-data.ts): MARKET_DATA is the R2 binding
  // declared in wrangler.toml, MARKET_DATA_ALLOWED_ORIGINS the CORS allowlist.
  // Neither is container runtime env -- do not add them to an envVars block.
  MARKET_DATA: R2Bucket;
  MARKET_DATA_ALLOWED_ORIGINS?: string;
  // Folded dashboard-api (#4687) env passthrough. All optional: unset means
  // the stub lane (local tests, secretless dev), exactly like the standalone
  // worker. No values ship in this slice — the standalone worker stays
  // deployed until cutover; secrets land via `wrangler secret put` later.
  SUPABASE_URL?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  MARKET_DATA_URL?: string;
  DASHBOARD_API_ALLOWED_ORIGINS?: string;
  // Retired digichat fold (#4689, dropped 2026-10-19). These names are still
  // declared in wrangler.toml [vars]/secrets for this Worker, but the
  // DigiChatContainer that forwarded them is gone (digichat lives in
  // apps/digichat-cloudflare) and no remaining envVars block reads them. They
  // are typed here so the deployed config stays described; env-vars-pin.test.js
  // pins that they are forwarded to no container.
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
  DIGICHAT_PLAN_PROOF_SECRET?: string;
  DIGICHAT_MONITOR_TOKENS?: string;
  DIGICHAT_DASHBOARD_SUPABASE_URL?: string;
  DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY?: string;
  /** DIG-3585 /chat/occ shell gate. Worker-scoped; never forwarded to a container. */
  OCC_INVITE_KEY?: string;
  /**
   * DIG-3814: short sha of the deploying commit, injected by this Worker's own
   * deploy wrapper (`scripts/deploy.mjs`, which shares the rev logic with the
   * digichat wrapper) via `wrangler deploy --var DIGICHAT_CONTAINER_REV:<sha12>`.
   * The Worker reads it to report the digichat Container id this commit derives
   * (see `sharedDigichatContainerId`). It mounts no digichat container since the
   * 2026-10-19 separation, so there is no `envVars` to forward it into;
   * env-vars-pin.test.js pins that no container block reads it.
   */
  DIGICHAT_CONTAINER_REV?: string;
}

/** Secret-gated MCP edge paths (`/_stack/mcp/<id>/…`) → in-container ports. */
const MCP_EDGE_PREFIX = "/_stack/mcp";
const MCP_EDGE_SERVERS: Record<string, number> = {
  digisearch: 8765,
  digivault: 8769,
};

/** Edge key for one server: an MCP_EDGE_KEYS entry wins, else the shared key. */
function mcpEdgeKeyFor(serverId: string, workerEnv: Env): string {
  const fallback = workerEnv.MCP_EDGE_KEY?.trim() ?? "";
  const raw = workerEnv.MCP_EDGE_KEYS?.trim();
  if (!raw) {
    return fallback;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      const value = (parsed as Record<string, unknown>)[serverId];
      if (typeof value === "string" && value.trim()) {
        return value.trim();
      }
    }
  } catch {
    // fall back to the shared key
  }
  return fallback;
}

function rewriteKeyStackPath(request: Request): Request {
  const url = new URL(request.url);
  const stripped = url.pathname.replace(/^\/_stack\/key/, "") || "/";
  url.pathname = stripped;
  return new Request(url.toString(), request);
}

function isMcpHostname(hostname: string): boolean {
  return hostname.trim().toLowerCase() === DIGIQUANT_MCP_HOSTNAME;
}

/**
 * The ONE place this Worker addresses the shared stack Container (DIG-3229).
 *
 * The Durable Object id is derived from the deploying commit
 * (`STACK_CONTAINER_REV`, injected by scripts/deploy.mjs), so every deploy
 * addresses a fresh instance instead of relying on the platform retiring the
 * old one — `sleepAfter` does not evict a Container under steady traffic, and
 * the hand-edited id that used to cover for that was forgotten twice (v16→v17
 * PII re-ingest; v17→v18 digikey scope escalation). See ports.ts for the full
 * history.
 *
 * Routing every shared-stack fetch through one helper is what makes a missed
 * site impossible: there is no second place that could hand `getContainer` an
 * id without the rev. src/container-id-deploy.test.js pins that this is the only
 * `getContainer(workerEnv.STACK, ...)` call in the file.
 */
function stackContainer(workerEnv: Env): DurableObjectStub<DigiStackContainer> {
  return getContainer(
    workerEnv.STACK,
    sharedStackContainerId(workerEnv.STACK_CONTAINER_REV),
  );
}

export default {
  async fetch(request: Request, workerEnv: Env): Promise<Response> {
    const url = new URL(request.url);
    // The OCC invite gate is NOT applied here: the invite-gated shell
    // (`/chat/occ*`) belongs to apps/digichat-cloudflare, which owns that route
    // and holds OCC_INVITE_KEY (Chris, 2026-10-19 — client surface off the base
    // platform). This Worker serves only graph./key./search.digithings.ai.
    if (url.pathname === "/_stack/meta") {
      // containerId is derived from the deploying commit (DIG-3229), so it is
      // the operator's proof that the running instance came from this deploy
      // rather than from a stale one. stackRev is null exactly when the build
      // carries no rev and the id fell back to the pinned legacy value.
      return Response.json({
        ok: true,
        service: "digithings-stack",
        containerId: sharedStackContainerId(workerEnv.STACK_CONTAINER_REV),
        stackRev: stackContainerRev(workerEnv.STACK_CONTAINER_REV),
        // DIG-3814: the digichat Container id for this same deploying commit,
        // derived by the standalone worker's own paths.ts and re-exported
        // through ./digichat, so one read-back verifies the rev reached both
        // Workers. This Worker does not serve digichat paths since the
        // 2026-10-19 separation and mounts no digichat container; the field is
        // reported for the shared deploy path's verification, not as a route
        // this Worker answers.
        digichatContainerId: sharedDigichatContainerId(workerEnv.DIGICHAT_CONTAINER_REV),
        digichatRev: digichatContainerRev(workerEnv.DIGICHAT_CONTAINER_REV),
        note: "Worker up; container ports may still be starting",
      });
    }

    // Per-module health (#4685): served directly, never touches a module
    // loader, so it stays up even when every route group is degraded.
    // Payload is state + last error message only — never secrets.
    if (url.pathname === "/_stack/status") {
      return Response.json(getStackStatus());
    }

    // workers.dev digikey probe without custom domain: /_stack/key/healthz
    if (url.pathname === "/_stack/key" || url.pathname.startsWith("/_stack/key/")) {
      // Lazy ports import per route group (#4685): a failing import degrades
      // only these paths (503); every other group keeps serving.
      return runIsolated("key-proxy", () => import("./ports"), async ({ DIGIKEY_PORT }) => {
        const container = stackContainer(workerEnv);
        // DIG-4477: a recycled container must not fail the client request —
        // the Durable Object id is a NAME, so one fresh attempt reaches the
        // live instance (see ./container-retry.ts). The clone per attempt is
        // what makes the replay possible: a consumed body cannot be re-sent.
        return fetchWithContainerRetry(() =>
          container.fetch(
            switchPort(rewriteKeyStackPath(request.clone()), DIGIKEY_PORT),
          ),
        );
      });
    }

    // In-container MCP servers for the OCC embed, reached over secret-gated edge
    // paths. The container-internal servers cannot be resolved from the
    // Cloudflare runtime (/etc/hosts is read-only), so digigraph dials this
    // public HTTPS path instead. Two credentials are accepted (./mcp-edge-auth):
    // a digikey JWT carrying `mcp:<serverId>`, or the static x-digi-mcp-key the
    // embed tenant entry carries (#3841 authHeader) for compose/self-host. Fail
    // closed: neither credential valid -> 401; valid JWT, wrong server -> 403.
    if (url.pathname.startsWith(`${MCP_EDGE_PREFIX}/`)) {
      const rest = url.pathname.slice(MCP_EDGE_PREFIX.length + 1);
      const slash = rest.indexOf("/");
      const serverId = slash === -1 ? rest : rest.slice(0, slash);
      const port = MCP_EDGE_SERVERS[serverId];
      if (typeof port === "number") {
        const decision = await authorizeMcpEdge({
          request,
          serverId,
          expectedKey: mcpEdgeKeyFor(serverId, workerEnv),
          env: workerEnv,
        });
        if (!decision.ok) {
          // The body names neither the credential nor the reason: the status is
          // the whole answer to the caller, and the decision log has the rest.
          return new Response(
            decision.status === 403
              ? "digithings-stack: forbidden"
              : "digithings-stack: unauthorized",
            {
              status: decision.status,
              headers: { "www-authenticate": 'Bearer realm="digikey"' },
            },
          );
        }
        // Lazy ports import per route group (#4685): a failing import
        // degrades only these paths (503); the fail-closed refusal above stays
        // synchronous and untouched.
        return runIsolated("mcp-edge", () => import("./ports"), async ({}) => {
          // Forward the client path unchanged: mcp>=1.26 serves `/mcp` and
          // 307s `/mcp/`, and a rewritten path breaks clients that do not
          // replay the body on the redirect.
          const stripped = slash === -1 ? "/" : rest.slice(slash);
          const target = new URL(url.toString());
          target.pathname = stripped;
          const container = stackContainer(workerEnv);
          // DIG-4477: retry once on a recycled container (see
          // ./container-retry.ts); the clone per attempt is what makes the
          // replay possible.
          return fetchWithContainerRetry(() => {
            const forwarded = new Request(target.toString(), request.clone());
            return container.fetch(switchPort(forwarded, port));
          });
        });
      }
    }

    // Read-only R2 market data (#4013 Task 8): public JSON for browser surfaces
    // (decision D1), served by the Worker itself — not proxied to the container.
    // Replaces the retired anon-readable Supabase market tables/views (dropped
    // in migration 127, #4053); no writes, no auth, CORS limited to
    // MARKET_DATA_ALLOWED_ORIGINS.
    if (url.pathname === "/v1/market/tickers" || url.pathname === "/v1/market/closes") {
      // Lazy market-data import (#4685): hyparquet evaluation is deferred to
      // the first market-data request, and a failing import degrades only
      // these paths (503).
      return runIsolated("market-data", () => import("./market-data"), async ({ handleMarketData }) => {
        return handleMarketData(request, workerEnv, url);
      });
    }

    // Folded dashboard-api (#4687): same handlers as the standalone worker,
    // served under the canonical module path. CORS allowlist behavior is the
    // standalone worker's own code (exact-match origins), so it stays
    // identical through the fold. A dashboard-api failure degrades only these
    // paths (503); the /_stack/mcp/* proxy above is untouched.
    if (url.pathname === "/dashboard-api" || url.pathname.startsWith("/dashboard-api/")) {
      // Lazy dashboard-api import: the folded route subgraph (portfolio,
      // allocations, brief, performance, kpis/live, nav-series, benchmarks,
      // ledger, /v1/tables/*, MCP tools) loads on first use here.
      return runIsolated(
        "dashboard-api",
        () => import("./dashboard-api"),
        async ({ handleDashboardApi }) => {
          return handleDashboardApi(request, workerEnv, url);
        },
      );
    }

    // The digichat product surface (and OCC, one of its tenants) is NOT served
    // here (Chris, 2026-10-19): it belongs to apps/digichat-cloudflare on the
    // `digithings-digichat` Worker and its own container. The folded-digichat
    // branch (#4689) and its route declarations were removed so the client
    // surface never rides the base platform, and so a deploy of this Worker
    // stops fighting another Worker for the same digithings.ai routes.

    // Dedicated digiquant-mcp container (#3780 Task 8): reachable only via the
    // reserved mcp.digithings.ai hostname once its route is enabled (HUMAN GATE
    // in wrangler.toml — needs Worker-edge digikey JWT enforcement first; the
    // MCP tools are unauthenticated localhost today). No workers.dev forwarding
    // route ships: an unauthenticated /_stack/mcp/* forwarder must not go live.
    if (isMcpHostname(url.hostname)) {
      // Lazy ports import per route group (#4685).
      return runIsolated("container-routes", () => import("./ports"), async ({ MCP_CONTAINER_ID }) => {
        const container = getContainer(workerEnv.MCP_STACK, MCP_CONTAINER_ID);
        // DIG-4477: retry once on a recycled container (see
        // ./container-retry.ts). DIG-4928: the answer for a hop that rejected
        // with a value that is not an Error names the container it came from.
        return fetchWithContainerRetry(() => container.fetch(request.clone()), {
          service: "mcp",
        });
      });
    }

    // Lazy ports import per route group (#4685): unknown-host 404 and the
    // shared-container proxy degrade only under this group on failure.
    return runIsolated("container-routes", () => import("./ports"), async ({ portForHostname }) => {
      const port = portForHostname(url.hostname);
      if (port === null) {
        return new Response(
          "digithings-stack: unknown host. Use graph.digithings.ai, " +
            "key.digithings.ai, or search.digithings.ai. " +
            "(mcp.digithings.ai is reserved; its route is not yet enabled.)",
          { status: 404 },
        );
      }
      // Wake hygiene: scanners and liveness probes never boot the Container.
      if (isScannerPath(url.pathname)) {
        return scannerResponse();
      }
      const container = stackContainer(workerEnv);
      if (isHealthProbe(request, url.pathname)) {
        let status: string | undefined;
        try {
          status = (await container.getState()).status;
        } catch {
          status = undefined;
        }
        if (!containerIsAwake(status)) {
          return sleepingHealthResponse(request);
        }
      }
      // DIG-4477: retry once on a recycled container (see
      // ./container-retry.ts). The clone per attempt is what makes the replay
      // possible: a consumed body cannot be re-sent.
      return fetchWithContainerRetry(() =>
        container.fetch(switchPort(request.clone(), port)),
      );
    });
  },
};
