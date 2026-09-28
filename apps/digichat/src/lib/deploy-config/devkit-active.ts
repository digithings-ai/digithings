/**
 * Dev-only active-config override for the /devkit preview loop (#4691).
 *
 * Lets a navigation (`/?mode=product&config=<file>.yaml` or
 * `/embed?config=<file>.yaml`) switch which config file this process serves —
 * process-global, exactly like changing DIGICHAT_CONFIG_PATH at runtime
 * (last navigation wins). Every read goes through getDigichatConfig(), which
 * consults this state only when NODE_ENV !== "production"; in production the
 * state is never read and never set (callers guard too), so there is zero
 * production surface and no new API.
 *
 * Server-only — never import from client components.
 */

const REL_RE = /^[\w.-]+(?:\/[\w.-]+)*\.yaml$/;

let active: string | null = null;

/** Set (or clear with null) the config filename under `config/` to serve. */
export function setDevkitActiveConfig(rel: string | null): void {
  active = rel;
}

/** Currently forced config filename, or null for the normal singleton. */
export function getDevkitActiveConfig(): string | null {
  return active;
}

function isSafeRel(rel: string): boolean {
  // No `..`/`.` segments — the char class alone would allow `..` as a segment,
  // and join() would resolve it outside config/.
  if (rel.split("/").some((s) => s === ".." || s === ".")) return false;
  return REL_RE.test(rel);
}

/**
 * Validate a `?config=` query/searchParams value: a bare config-tree filename
 * (one level or `examples/<name>.yaml`, no traversal). `clear`/absent → null
 * (back to the singleton). Invalid values → undefined (caller keeps current
 * behavior).
 */
export function parseDevkitConfigParam(
  raw: string | string[] | undefined | null,
): string | null | undefined {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (v === undefined || v === null || v === "") return null;
  if (v === "clear") return null;
  return isSafeRel(v) ? v : undefined;
}
