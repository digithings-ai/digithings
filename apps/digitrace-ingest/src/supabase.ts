/**
 * PostgREST, the index's only write path.
 *
 * ADR-0036 §3: the consumer reaches Supabase over PostgREST/REST, the only
 * precedented Worker-to-Supabase path in this repository. A raw Postgres driver
 * is DIG-2658's Hyperdrive decision and is not used here.
 *
 * The service role bypasses RLS, so the tenant boundary on this path is the
 * application-layer `workspace_id` filter (ADR-0036 §5): every row this module
 * writes carries the `workspace_id` resolved from the verified tenant slug, and
 * nothing here accepts a `workspace_id` from a queue payload.
 */

export class SupabaseConfigError extends Error {
  constructor(missing: string) {
    super(`supabase is not configured: ${missing} is unset`);
    this.name = "SupabaseConfigError";
  }
}

export class SupabaseError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "SupabaseError";
  }
}

export interface SupabaseConfig {
  url: string;
  key: string;
}

/** The configured project, or a named error. Never falls back to a default. */
export function supabaseConfig(env: {
  SUPABASE_URL?: string;
  CORE_SUPABASE_SERVICE_KEY?: string;
}): SupabaseConfig {
  const url = (env.SUPABASE_URL ?? "").trim();
  const key = (env.CORE_SUPABASE_SERVICE_KEY ?? "").trim();
  if (url === "") throw new SupabaseConfigError("SUPABASE_URL");
  if (key === "") throw new SupabaseConfigError("CORE_SUPABASE_SERVICE_KEY");
  return { url: url.replace(/\/+$/, ""), key };
}

/**
 * A PostgREST error, described without the row it was about.
 *
 * PostgREST's error body can echo the offending values in `details` and `hint`,
 * which for this Worker is span content in a log line. Only `message` and
 * `code` — schema-level facts — are kept.
 */
function describeFailure(status: number, body: string): string {
  try {
    const parsed = JSON.parse(body) as { message?: unknown; code?: unknown };
    const message = typeof parsed.message === "string" ? parsed.message : "";
    const code = typeof parsed.code === "string" ? parsed.code : "";
    const detail = message === "" ? code : code === "" ? message : `${message} (${code})`;
    return `PostgREST ${status}${detail ? `: ${detail}` : ""}`;
  } catch {
    return `PostgREST ${status}`;
  }
}

/** One request against the project's REST API. */
export async function restRequest(
  env: { SUPABASE_URL?: string; CORE_SUPABASE_SERVICE_KEY?: string },
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const { url, key } = supabaseConfig(env);
  const headers = new Headers(init.headers);
  headers.set("apikey", key);
  headers.set("authorization", `Bearer ${key}`);
  headers.set("accept", "application/json");
  if (init.body !== undefined) headers.set("content-type", "application/json");
  return fetch(`${url}/rest/v1/${path}`, { ...init, headers });
}

/**
 * The `workspaces.id` for a tenant slug, resolved once on the core side.
 *
 * Throws when the slug is unknown: an index row with no workspace is not
 * writable, and skipping it silently would turn a misconfigured tenant into
 * missing traces.
 */
export async function resolveWorkspaceId(
  env: { SUPABASE_URL?: string; CORE_SUPABASE_SERVICE_KEY?: string },
  slug: string,
): Promise<string> {
  const query = `workspaces?slug=eq.${encodeURIComponent(slug)}&select=id&limit=1`;
  const response = await restRequest(env, query);
  if (!response.ok) {
    throw new SupabaseError(
      response.status,
      describeFailure(response.status, await response.text()),
    );
  }
  const rows = (await response.json()) as Array<{ id?: unknown }>;
  const id = Array.isArray(rows) && rows.length === 1 ? rows[0]?.id : undefined;
  if (typeof id !== "string" || id === "") {
    throw new SupabaseError(404, `workspace not found for tenant ${slug}`);
  }
  return id;
}

/**
 * Upsert rows, idempotently.
 *
 * `onConflict` names the natural key, so a retried queue message rewrites the
 * same rows instead of duplicating them. The caller must have made every column
 * a function of the message, never of the clock: that is what makes the retry
 * safe.
 */
export async function upsertRows(
  env: { SUPABASE_URL?: string; CORE_SUPABASE_SERVICE_KEY?: string },
  table: string,
  rows: Array<Record<string, unknown>>,
  onConflict: string,
): Promise<void> {
  if (rows.length === 0) return;
  const response = await restRequest(
    env,
    `${table}?on_conflict=${encodeURIComponent(onConflict)}`,
    {
      method: "POST",
      headers: {
        // merge-duplicates turns the POST into an upsert; return=minimal keeps the
        // response small on a hot path and is all this Worker needs.
        prefer: "resolution=merge-duplicates,return=minimal",
      },
      body: JSON.stringify(rows),
    },
  );
  if (!response.ok) {
    throw new SupabaseError(
      response.status,
      describeFailure(response.status, await response.text()),
    );
  }
}
