import { getEcosystemEndpoints } from "@/lib/ecosystem";
import { isServiceCapabilityEnabled } from "@/lib/capabilities";

export const dynamic = "force-dynamic";

async function ping(url: string, ms: number): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    const r = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
    clearTimeout(t);
    if (!r.ok) return false;
    // Stack worker answers liveness probes without booting the container
    // ({container:"sleeping"}); that is not "ready".
    const txt = await r.text().catch(() => "");
    return !/"container"\s*:\s*"sleeping"/.test(txt);
  } catch {
    return false;
  }
}

/**
 * Boots the services chat depends on, in order (auth -> graph -> search),
 * and reports per-service readiness. No internals or secrets in the output.
 */
export async function GET() {
  const eco = await getEcosystemEndpoints();
  const out: Record<string, "ready" | "waking"> = {};
  const key = process.env.DIGIKEY_URL?.trim();
  if (key) out.auth = (await ping(`${key.replace(/\/$/, "")}/.well-known/jwks.json`, 25_000)) ? "ready" : "waking";
  if (isServiceCapabilityEnabled("digigraph"))
    out.assistant = (await ping(`${eco.digigraphUrl.replace(/\/$/, "")}/health`, 25_000)) ? "ready" : "waking";
  if (eco.digisearchUrl?.trim())
    out.search = (await ping(`${eco.digisearchUrl.replace(/\/$/, "")}/health`, 15_000)) ? "ready" : "waking";
  const ready = Object.values(out).every((v) => v === "ready");
  return Response.json({ ready, services: out }, { status: 200, headers: { "cache-control": "no-store" } });
}
