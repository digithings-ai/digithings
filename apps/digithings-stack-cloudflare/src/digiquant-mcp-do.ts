/**
 * Durable Object host for the Worker-native digiquant market-data MCP (DIG-2913).
 *
 * Why a DO and not a plain stateless Worker: the Python read path cached fresh
 * windows for 900s in process memory, and that cache is the reason the MCP
 * container was pinned to one replica (`max_instances = 1`, `MCP_CONTAINER_ID`).
 * A Durable Object keeps the same single-instance cache semantics without a
 * Firecracker boot: one instance owns the endpoint, the cache is a plain Map in
 * `this`, and an eviction only means a cold cache (the next call re-reads R2).
 *
 * The MCP protocol itself is stateless (no session ids, JSON responses), so a
 * DO restart is invisible to clients.
 *
 * `cloudflare:workers` is imported here, not in `digiquant-mcp.ts`, so the read
 * path and its tools stay importable from vitest under node.
 */
import { DurableObject } from "cloudflare:workers";
import { type CacheStore, handleDigiQuantMcp, type R2BucketLike } from "./digiquant-mcp";
import type { JwksCacheKv } from "./mcp-edge-auth";

export interface DigiQuantMcpEnv {
  /** Same archive bucket `/v1/market/*` reads (`digithings-archive`). */
  MARKET_DATA: R2Bucket;
  /** Static edge key accepted as `x-digi-mcp-key`; absent disables that path. */
  MCP_EDGE_KEY?: string;
  /** digikey JWKS endpoint; absent disables the `Authorization: Bearer` path. */
  DIGIKEY_JWKS_URL?: string;
  /** Expected `iss` / `aud` for the JWT path (see ./mcp-edge-auth). */
  DIGIKEY_ISSUER?: string;
  DIGIKEY_AUDIENCE?: string;
  /**
   * Service binding to this same Worker. `key.digithings.ai` is one of its own
   * routes, so a plain `fetch` for the JWKS from inside cannot complete; the
   * binding keeps the subrequest inside the Worker (see ./mcp-edge-auth).
   */
  DIGIKEY_SELF?: { fetch(input: string, init?: RequestInit): Promise<Response> };
  /**
   * Read-through KV cache for the public JWKS, so a cold digikey cannot 401
   * every MCP call (`MCP_EDGE_JWKS_KV_KEY` in ./mcp-edge-auth).
   */
  TENANT_CONFIG?: JwksCacheKv;
  /** The stack's own KV; preferred over TENANT_CONFIG when bound. */
  STACK_CACHE?: JwksCacheKv;
}

export class DigiQuantMcpAgent extends DurableObject<DigiQuantMcpEnv> {
  /** Python `_ttl`: 900s of fresh payloads, per instance. */
  private readonly cache: CacheStore = new Map();

  override async fetch(request: Request): Promise<Response> {
    return handleDigiQuantMcp(request, {
      bucket: this.env.MARKET_DATA as unknown as R2BucketLike,
      edgeKey: this.env.MCP_EDGE_KEY,
      authEnv: {
        DIGIKEY_JWKS_URL: this.env.DIGIKEY_JWKS_URL,
        DIGIKEY_ISSUER: this.env.DIGIKEY_ISSUER,
        DIGIKEY_AUDIENCE: this.env.DIGIKEY_AUDIENCE,
        // Same JWKS route as `/_stack/mcp/*`: the service binding keeps the
        // subrequest inside this Worker, and the KV entry survives a cold
        // digikey. Without both, the JWT path fails closed on every call.
        DIGIKEY_SELF: this.env.DIGIKEY_SELF,
        TENANT_CONFIG: this.env.TENANT_CONFIG,
        STACK_CACHE: this.env.STACK_CACHE,
      },
      cache: this.cache,
    });
  }
}
