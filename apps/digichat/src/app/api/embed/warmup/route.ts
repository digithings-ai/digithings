import { getEcosystemEndpoints } from "@/lib/ecosystem";
import { isServiceCapabilityEnabled } from "@/lib/capabilities";
import { getDigichatConfig } from "@/lib/deploy-config/loader";

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
 * Boots the services chat depends on, in order (auth, then assistant, then
 * search when this container is configured for it), and reports per-service
 * readiness. No internals or secrets in the output. Same route for every
 * tenant — which services exist is deployment config, not a host branch.
 */
/**
 * Whether this deployment talks to digigraph at all.
 *
 * A Foundry-backed install has no digigraph to warm, but the default enabled
 * service set names it, so the gate used to probe an endpoint that does not
 * exist and park the UI on a boot screen (#6023). The old escape hatch --
 * DIGICHAT_ENABLED_SERVICES=foundry -- named a service outside the capability
 * list, so it silenced every probe rather than the right one. Fail open: an
 * unreadable config is probed as before.
 */
function deploymentUsesDigigraph(): boolean {
  try {
    const backend = getDigichatConfig().deployment?.backend;
    return backend?.type !== "foundry";
  } catch {
    return true;
  }
}

export async function GET() {
  const eco = await getEcosystemEndpoints();
  const out: Record<string, "ready" | "waking"> = {};
  const key = process.env.DIGIKEY_URL?.trim();
  if (key) {
    out.auth = (await ping(`${key.replace(/\/$/, "")}/.well-known/jwks.json`, 25_000))
      ? "ready"
      : "waking";
  }
  if (isServiceCapabilityEnabled("digigraph") && deploymentUsesDigigraph()) {
    out.assistant = (await ping(`${eco.digigraphUrl.replace(/\/$/, "")}/health`, 25_000))
      ? "ready"
      : "waking";
  }
  const searchUrl = process.env.DIGISEARCH_INTERNAL_URL?.trim();
  if (searchUrl && isServiceCapabilityEnabled("digisearch")) {
    out.search = (await ping(`${searchUrl.replace(/\/$/, "")}/health`, 15_000)) ? "ready" : "waking";
  }
  const ready = Object.values(out).every((v) => v === "ready");
  return Response.json(
    { ready, services: out },
    { status: 200, headers: { "cache-control": "no-store" } },
  );
}
