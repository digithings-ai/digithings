import { cookies } from "next/headers";

import { isServiceCapabilityEnabled } from "@/lib/capabilities";

export const ENDPOINTS_COOKIE = "digichat-endpoints";

export type EcosystemEndpoints = {
  digigraphUrl: string;
  digiquantUrl: string;
  digismithUrl: string;
  /** Optional when digisearch is not in DIGICHAT_ENABLED_SERVICES */
  digisearchUrl?: string;
};

const DEFAULTS: EcosystemEndpoints = {
  digigraphUrl:
    process.env.DIGIGRAPH_INTERNAL_URL?.replace(/\/$/, "") ??
    "http://127.0.0.1:8000",
  digiquantUrl:
    process.env.DIGIQUANT_INTERNAL_URL?.replace(/\/$/, "") ??
    "http://127.0.0.1:8001",
  digismithUrl:
    process.env.DIGISMITH_INTERNAL_URL?.replace(/\/$/, "") ??
    "http://127.0.0.1:8003",
  digisearchUrl:
    process.env.DIGISEARCH_INTERNAL_URL?.replace(/\/$/, "") ??
    "http://127.0.0.1:8002",
};

/**
 * Loose SSRF guard: http(s) only, no userinfo, reasonable host.
 */
export function isAllowedServiceUrl(raw: string): boolean {
  let u: URL;
  try {
    u = new URL(raw.trim());
  } catch {
    return false;
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return false;
  if (u.username || u.password) return false;
  const host = u.hostname;
  if (!host || host === "0.0.0.0") return false;
  const allow = (process.env.DIGICHAT_ENDPOINT_HOST_ALLOWLIST ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (allow.length && !allow.includes(host)) {
    return allow.some((h) => host === h || host.endsWith(`.${h}`));
  }
  if (host === "localhost" || host === "127.0.0.1") return true;
  if (host.endsWith(".local")) return true;
  if (/^[a-z0-9-]+$/.test(host)) return true; // docker service names (digigraph, digiquant, …)
  const priv =
    /^10\.\d+\.\d+\.\d+$/.test(host) ||
    /^192\.168\.\d+\.\d+$/.test(host) ||
    /^172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+$/.test(host);
  if (priv) {
    return process.env.DIGICHAT_ALLOW_PRIVATE_ENDPOINTS === "1";
  }
  return false;
}

function normalizeBase(u: string): string {
  return u.trim().replace(/\/$/, "");
}

/** Drop or fill DigiSearch URL based on DIGICHAT_ENABLED_SERVICES. */
export function withDigisearchCapability(e: EcosystemEndpoints): EcosystemEndpoints {
  const out = { ...e };
  if (!isServiceCapabilityEnabled("digisearch")) {
    delete out.digisearchUrl;
    return out;
  }
  if (!out.digisearchUrl?.trim() && DEFAULTS.digisearchUrl) {
    out.digisearchUrl = DEFAULTS.digisearchUrl;
  }
  return out;
}

export function parseEndpointsPayload(raw: unknown): EcosystemEndpoints | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const dg = typeof o.digigraphUrl === "string" ? o.digigraphUrl : "";
  const dq = typeof o.digiquantUrl === "string" ? o.digiquantUrl : "";
  const ds = typeof o.digismithUrl === "string" ? o.digismithUrl : "";
  const dsearch =
    typeof o.digisearchUrl === "string" && o.digisearchUrl.trim()
      ? o.digisearchUrl
      : undefined;
  if (!dg || !dq || !ds) return null;
  if (!isAllowedServiceUrl(dg) || !isAllowedServiceUrl(dq) || !isAllowedServiceUrl(ds))
    return null;
  if (dsearch && !isAllowedServiceUrl(dsearch)) return null;
  const out: EcosystemEndpoints = {
    digigraphUrl: normalizeBase(dg),
    digiquantUrl: normalizeBase(dq),
    digismithUrl: normalizeBase(ds),
  };
  if (dsearch) out.digisearchUrl = normalizeBase(dsearch);
  return out;
}

export async function getEcosystemEndpoints(): Promise<EcosystemEndpoints> {
  const jar = await cookies();
  const raw = jar.get(ENDPOINTS_COOKIE)?.value;
  if (!raw) {
    return withDigisearchCapability({ ...DEFAULTS });
  }
  try {
    const parsed = parseEndpointsPayload(JSON.parse(raw) as unknown);
    if (parsed) {
      return withDigisearchCapability(parsed);
    }
  } catch {
    /* use defaults */
  }
  return withDigisearchCapability({ ...DEFAULTS });
}

export function getEcosystemDefaults(): EcosystemEndpoints {
  return withDigisearchCapability({ ...DEFAULTS });
}
