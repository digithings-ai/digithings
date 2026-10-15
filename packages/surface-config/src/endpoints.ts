/**
 * Surfaces 1.0 endpoint resolution (ADR D5).
 * Zero dependencies — Bun, Node, and Next server code can import this.
 * DIG-2703 owns CSP / port pinning and cloud MCP host approval.
 */

export type SurfaceService = "desk" | "chat" | "mcp" | "graph" | "stack";

type Profile = "local" | "cloud";

const LOCAL: Record<SurfaceService, string | undefined> = {
  desk: "http://127.0.0.1:8788",
  chat: "http://127.0.0.1:3000",
  mcp: "http://127.0.0.1:8787/mcp",
  graph: undefined,
  stack: undefined,
};

const CLOUD: Record<SurfaceService, string | undefined> = {
  desk: "https://dashboard-api.chris-stefan.workers.dev",
  chat: "https://digithings.ai",
  mcp: undefined,
  graph: "https://graph.digithings.ai",
  stack: undefined,
};

function trimUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

function profileOf(env: NodeJS.ProcessEnv = process.env): Profile {
  return env.DIGI_ENV === "cloud" ? "cloud" : "local";
}

function envUrl(service: SurfaceService, env: NodeJS.ProcessEnv): string | undefined {
  const key = `DIGI_${service.toUpperCase()}_URL`;
  const raw = env[key];
  if (typeof raw === "string" && raw.trim()) return trimUrl(raw);
  return undefined;
}

/** Deprecated one-release aliases (ADR D5). */
function deprecatedAlias(service: SurfaceService, env: NodeJS.ProcessEnv): string | undefined {
  if (service === "desk") {
    const raw = env.DQ_API_URL;
    if (typeof raw === "string" && raw.trim()) return trimUrl(raw);
  }
  if (service === "chat") {
    const raw = env.DIGICHAT_DEVKIT_URL;
    if (typeof raw === "string" && raw.trim()) return trimUrl(raw);
  }
  return undefined;
}

/**
 * Resolve a surface service base URL.
 * Order: DIGI_<SERVICE>_URL → deprecated alias → DIGI_ENV profile default → throw.
 */
export function endpoint(service: SurfaceService, env: NodeJS.ProcessEnv = process.env): string {
  const fromEnv = envUrl(service, env);
  if (fromEnv) return fromEnv;
  const alias = deprecatedAlias(service, env);
  if (alias) return alias;
  const profile = profileOf(env);
  const defaults = profile === "cloud" ? CLOUD : LOCAL;
  const value = defaults[service];
  if (!value) {
    throw new Error(`endpoint("${service}") is unset for DIGI_ENV=${profile}`);
  }
  return value;
}
