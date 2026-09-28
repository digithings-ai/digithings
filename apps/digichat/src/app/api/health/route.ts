import { sql } from "drizzle-orm";
import { getDb } from "@/db";
import { getEcosystemEndpoints } from "@/lib/ecosystem";
import { isServiceCapabilityEnabled } from "@/lib/capabilities";
import { getLicenseState } from "@/lib/license/state";
import { resolveDigichatVersion } from "@/lib/license/version";

async function pingHealth(base: string, label: string, checks: Record<string, string>) {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000);
    const r = await fetch(`${base.replace(/\/$/, "")}/health`, { signal: ctrl.signal });
    clearTimeout(t);
    checks[label] = r.ok ? "ok" : `http_${r.status}`;
  } catch {
    checks[label] = "unreachable";
  }
}

export async function GET() {
  const checks: Record<string, string> = {
    service: "ok",
  };

  const eco = await getEcosystemEndpoints();
  // digigraph/digiquant/digismith always have a default URL (see ecosystem.ts
  // DEFAULTS), unlike digisearchUrl, so URL presence alone can't signal
  // "not deployed here" for them — check the capability flag directly.
  if (isServiceCapabilityEnabled("digigraph")) {
    await pingHealth(eco.digigraphUrl, "digraph", checks);
  }
  if (isServiceCapabilityEnabled("digiquant")) {
    await pingHealth(eco.digiquantUrl, "digiquant", checks);
  }
  if (isServiceCapabilityEnabled("digismith")) {
    await pingHealth(eco.digismithUrl, "digismith", checks);
  }
  if (eco.digisearchUrl?.trim()) {
    await pingHealth(eco.digisearchUrl, "digisearch", checks);
  }

  const db = getDb();
  if (db) {
    try {
      await db.execute(sql`SELECT 1`);
      checks.database = "ok";
    } catch {
      checks.database = "error";
    }
  } else {
    checks.database = "skipped";
  }

  const digraphOk = !isServiceCapabilityEnabled("digigraph") || checks.digraph === "ok";
  const digiquantOk = !isServiceCapabilityEnabled("digiquant") || checks.digiquant === "ok";
  const digismithOk = !isServiceCapabilityEnabled("digismith") || checks.digismith === "ok";
  const digisearchOk = !eco.digisearchUrl?.trim() || checks.digisearch === "ok";

  const ok =
    digraphOk &&
    digiquantOk &&
    digismithOk &&
    digisearchOk &&
    (checks.database === "ok" || checks.database === "skipped");

  // License state is reported honestly but never feeds the `ok`
  // computation: a revoked/expired license must not read as a downstream
  // outage and crash-loop the container. Turn-serving probes read
  // `license_status` instead.
  const license = getLicenseState();
  return Response.json(
    {
      ok,
      checks,
      version: resolveDigichatVersion(),
      license_status: license.state,
      ...(license.detail ? { license_detail: license.detail } : {}),
    },
    { status: ok ? 200 : 503 }
  );
}
