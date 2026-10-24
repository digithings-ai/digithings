/**
 * The edge gate for the OCC helpdesk MCP endpoint (DIG-5121).
 *
 * The endpoint has two spellings once the app is served under the base path:
 * the container-local one (/api/mcp/zammad/…, answered by the in-image
 * trusted proxy) and the base-path one (/chat/api/mcp/zammad/…, which the
 * app's own Next route would answer — and that route carries no auth of its
 * own). Both are gated here with the edge key the Worker holds, and the
 * base-path spelling is mapped back onto the container-local one so the
 * unauthenticated copy is never reached (see `containerLocalMcpPath`).
 *
 * The gate lives in its own module so the tests can EXECUTE it. A grep over
 * the Worker's source cannot tell a fail-closed gate from a fail-open one:
 * both read the same way, and only the answer does.
 */
import { containerLocalMcpPath } from "./paths";

/** The header the client sends the edge key in. */
export const MCP_KEY_HEADER = "x-digi-mcp-key";

export type McpGate =
  /** The path is not an MCP path at all: the caller routes it as usual. */
  | { kind: "not-mcp" }
  /** The path is an MCP path and the key matches. */
  | { kind: "authorized" }
  /** The path is an MCP path and the key is missing, wrong, or not set. */
  | { kind: "unauthorized" };

/**
 * The gate's verdict for one request.
 *
 * Fail-closed, in every direction: an unset expected key, a missing provided
 * key, and a mismatch are all "unauthorized". Only an exact match opens the
 * endpoint. An unset expected key is a configuration fault, and it closes the
 * endpoint rather than opening it.
 */
export function evaluateMcpGate(
  pathname: string,
  providedKey: string | null | undefined,
  expectedKey: string | null | undefined,
): McpGate {
  if (containerLocalMcpPath(pathname) === null) return { kind: "not-mcp" };
  const expected = (expectedKey ?? "").trim();
  const provided = (providedKey ?? "").trim();
  if (!expected || !provided || provided !== expected) return { kind: "unauthorized" };
  return { kind: "authorized" };
}
