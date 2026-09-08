/**
 * Operator MCP servers from deploy YAML (#3736).
 * URLs never reach the browser; the BFF forwards allowlisted https(s) URLs
 * to digigraph. Client-supplied MCP URLs are ignored.
 */

import type { DigichatDeployment } from "./schema";

const MCP_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const METADATA_HOSTS = new Set(["169.254.169.254", "metadata.google.internal"]);

/** Operator YAML MCP URL — https/http, no userinfo, no metadata IPs. */
export function isAllowedMcpServerUrl(raw: string): boolean {
  let u: URL;
  try {
    u = new URL(raw.trim());
  } catch {
    return false;
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return false;
  if (u.username || u.password) return false;
  const host = u.hostname.toLowerCase();
  if (!host || host === "0.0.0.0" || METADATA_HOSTS.has(host)) return false;
  if (host.endsWith(".internal")) return false;
  return true;
}

export type McpServerForward = { id: string; url: string };

export function operatorMcpServersForUpstream(
  dep: DigichatDeployment | null | undefined,
): McpServerForward[] {
  const out: McpServerForward[] = [];
  const seen = new Set<string>();
  for (const s of dep?.mcp?.servers ?? []) {
    const id = s.id.trim().toLowerCase();
    if (!MCP_ID.test(id) || seen.has(id)) continue;
    if (!isAllowedMcpServerUrl(s.url)) continue;
    seen.add(id);
    out.push({ id, url: s.url.trim() });
  }
  return out;
}

export function mcpServersHeaderValue(
  dep: DigichatDeployment | null | undefined,
): string | undefined {
  const servers = operatorMcpServersForUpstream(dep);
  if (!servers.length) return undefined;
  const json = JSON.stringify(servers);
  if (json.length > 8_192) return undefined;
  return json;
}
