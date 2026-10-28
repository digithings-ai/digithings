import { pickBackend } from "./backends";
import { BadRequest, parseSelect, validateUpsert } from "./query";
import { TWELVEX_TABLES } from "./tables.twelvex";
import type { DataEnv, TableSpec } from "./types";

const DBS: Record<string, Record<string, TableSpec>> = { twelvex: TWELVEX_TABLES };

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function authorized(req: Request, env: DataEnv): boolean {
  const want = env.DATA_API_TOKEN;
  if (!want) return false; // fail closed
  const got = req.headers.get("authorization") ?? "";
  if (got.length !== want.length + 7) return false;
  let diff = 0;
  const exp = `Bearer ${want}`;
  for (let i = 0; i < exp.length; i++) diff |= exp.charCodeAt(i) ^ got.charCodeAt(i);
  return diff === 0;
}

/** True for the paths this module owns. The runner routes them here first. */
export function isDataApiPath(pathname: string): boolean {
  return pathname === "/v1" || pathname.startsWith("/v1/");
}

/**
 * twelve-x data API (moved from the retired digidata-api Worker, DIG-2887 S2).
 * Served by twelvex-runner so the only Worker that binds the twelve-x database
 * binds nothing of core. No public hostname: callers reach it through the
 * runner's service binding.
 */
export async function handleDataApi(req: Request, env: DataEnv): Promise<Response> {
  const url = new URL(req.url);
  if (url.pathname === "/v1/health")
    return json({ ok: true, backend: (env.DATA_BACKEND ?? "supabase").toLowerCase() });
  if (!authorized(req, env)) return json({ error: "unauthorized" }, 401);
  const m = url.pathname.match(/^\/v1\/([a-z0-9_]+)\/([a-z0-9_]+)$/);
  if (!m) return json({ error: "not_found" }, 404);
  const [, db, table] = m;
  const spec = DBS[db]?.[table];
  if (!spec) return json({ error: "unknown_table" }, 404);
  try {
    const backend = pickBackend(env, db as "twelvex");
    if (req.method === "GET") {
      return json({
        backend: backend.name,
        rows: await backend.select(parseSelect(table, spec, url.searchParams)),
      });
    }
    if (req.method === "POST") {
      const q = validateUpsert(table, spec, await req.json(), url.searchParams.get("on_conflict"));
      return json({ backend: backend.name, ...(await backend.upsert(q)) });
    }
    return json({ error: "method_not_allowed" }, 405);
  } catch (e) {
    if (e instanceof BadRequest) return json({ error: e.message }, 400);
    if (e instanceof SyntaxError) return json({ error: "bad_json" }, 400);
    console.error("twelvex-data-api", String(e));
    return json({ error: "backend_error" }, 502);
  }
}
