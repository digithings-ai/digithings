"use client";

import { p } from "@/lib/base-path";

export const MCP_OAUTH_MESSAGE = "digichat-mcp-oauth";

export type McpOAuthResult = {
  id: string;
  accessToken?: string;
  error?: string;
};

export function listenMcpOAuthResult(onResult: (msg: McpOAuthResult) => void): () => void {
  const onMessage = (event: MessageEvent) => {
    if (event.origin !== window.location.origin) return;
    const data = event.data as { type?: unknown; id?: unknown; accessToken?: unknown; error?: unknown };
    if (!data || data.type !== MCP_OAUTH_MESSAGE) return;
    onResult({
      id: String(data.id ?? ""),
      ...(typeof data.accessToken === "string" ? { accessToken: data.accessToken } : {}),
      ...(typeof data.error === "string" ? { error: data.error } : {}),
    });
  };
  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}

export async function startMcpOAuth(input: {
  id: string;
  url?: string;
  clientId?: string;
  scopes?: string;
}): Promise<void> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  const host = new URLSearchParams(window.location.search).get("host");
  if (host) headers["X-Embed-Host"] = host;
  const res = await fetch(p("/api/mcp/oauth/start"), {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify({
      id: input.id,
      ...(input.url ? { url: input.url } : {}),
      ...(input.clientId ? { client_id: input.clientId } : {}),
      ...(input.scopes ? { scopes: input.scopes } : {}),
    }),
  });
  const data = (await res.json().catch(() => null)) as { authorizationUrl?: string; error?: string } | null;
  if (!res.ok || !data?.authorizationUrl) {
    throw new Error(data?.error || "Could not start OAuth.");
  }
  const popup = window.open(
    data.authorizationUrl,
    "dc-mcp-oauth",
    "width=480,height=720,popup=yes",
  );
  if (!popup) {
    throw new Error("Popup blocked. Allow popups to authenticate.");
  }
}
