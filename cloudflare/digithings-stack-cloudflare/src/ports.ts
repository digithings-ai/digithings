/** digigraph default edge port inside the Profile A stack Container. */
export const DIGIGRAPH_PORT = 8000;

/** digikey edge port inside the Profile A stack Container. */
export const DIGIKEY_PORT = 8005;

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

/** Single Durable Object / Container id for the shared Profile A stack.
 * Bump the suffix when a deploy must force a new Firecracker instance
 * (old DO can keep a stale image until sleepAfter expires).
 */
export const SHARED_STACK_CONTAINER_ID = "shared-v14";

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
  // wrangler.dev / workers.dev fallback: path-prefix routing not used;
  // default to digigraph so /healthz works on the workers.dev URL.
  if (host.endsWith(".workers.dev") || host === "localhost" || host === "127.0.0.1") {
    return DIGIGRAPH_PORT;
  }
  return null;
}
