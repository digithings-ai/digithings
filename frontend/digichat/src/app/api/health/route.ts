import { sql } from "drizzle-orm";
import { getDb } from "@/db";
import { getEcosystemEndpoints } from "@/lib/ecosystem";

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
  await pingHealth(eco.digigraphUrl, "digraph", checks);
  await pingHealth(eco.digiquantUrl, "digiquant", checks);
  await pingHealth(eco.digismithUrl, "digismith", checks);
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

  const digisearchOk = !eco.digisearchUrl?.trim() || checks.digisearch === "ok";

  const ok =
    checks.digraph === "ok" &&
    checks.digiquant === "ok" &&
    checks.digismith === "ok" &&
    digisearchOk &&
    (checks.database === "ok" || checks.database === "skipped");

  return Response.json(
    {
      ok,
      checks,
      version: process.env.DIGICHAT_VERSION ?? "0.1.0",
    },
    { status: ok ? 200 : 503 }
  );
}
