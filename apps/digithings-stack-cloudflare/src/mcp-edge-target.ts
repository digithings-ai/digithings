/**
 * URL the MCP edge hands to the container for one server.
 *
 * The in-container servers are Python `mcp` transports, and the SDK guards
 * them against DNS rebinding: a Host it cannot allow-list is answered 421
 * "Invalid Host header". It allow-lists the loopback names only WITH a port,
 * and only for a loopback-bound server, so forwarding the public Host
 * (search.digithings.ai) is refused. Routing does not depend on the Host —
 * switchPort sets cf-container-target-port — so the loopback spelling with the
 * in-container port is presented instead. Same reasoning as
 * scripts/zammad_mcp/server.py (DIG-5193).
 */
export function mcpEdgeTarget(url: URL, pathname: string, port: number): URL {
  const target = new URL(url.toString());
  target.pathname = pathname;
  target.hostname = "127.0.0.1";
  target.port = String(port);
  return target;
}
