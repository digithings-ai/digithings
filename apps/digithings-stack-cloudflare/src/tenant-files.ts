/**
 * Tenant files: per-tenant web-search site graphs and pre-crawled page corpora,
 * delivered from the `TENANT_CONFIG` KV namespace into the container at cold
 * start.
 *
 * Tenant config lives in KV only (Chris, 2026-10-15), never in repo files, so
 * these documents cannot be baked into the image. A Container's runtime env is
 * the one channel the Worker controls, so the bundle travels as env vars:
 *
 *   KV `DIGI_TENANT_FILES` = `{ "v": 1, "bundle": "<base64 of gzip(JSON)>" }`
 *   where the gzipped JSON is `{ "<relative path>": "<utf-8 text>", ... }` and
 *   every path is `sites/<id>.md` or `pages/<id>/<name>.md`.
 *
 * The Worker only splits the base64 into `DIGI_TENANT_FILES_<n>` chunks (each
 * well under the Containers runtime's per-variable limit, see
 * CONTAINER_ENV_VAR_MAX_BYTES) and names the two
 * directories the readers use. container/entrypoint.sh joins, decodes and
 * writes the files under /data/tenant-files, refusing any other path.
 *
 * FAIL CLOSED: an absent key, a KV error, malformed JSON, a wrong version or an
 * oversized bundle all yield NO env at all. With no files a pinned tenant keeps
 * its pin (that is enforced from the corpus map, not from these files); it
 * only loses the site map text and the challenge-page fallback. Nothing here
 * can widen what a tenant reaches, and a stack without the key starts with
 * byte-identical env.
 */

/** KV key holding the tenant-files bundle. */
export const TENANT_FILES_KEY = "DIGI_TENANT_FILES";

/** Where entrypoint.sh unpacks the bundle (under the container's /data). */
export const TENANT_FILES_ROOT = "/data/tenant-files";

/**
 * Hard per-variable limit the Containers runtime enforces when a container
 * starts: a larger value fails the start with "the size of the env variable
 * exceeds the limit of 16000 bytes", so every request to the container 503s.
 * Not in the public limits page; observed on a production start.
 */
export const CONTAINER_ENV_VAR_MAX_BYTES = 16_000;

/**
 * Per-env-var chunk size (base64, so one byte per character). Leaves room for
 * the variable name and any `NAME=` framing under CONTAINER_ENV_VAR_MAX_BYTES.
 */
export const TENANT_FILES_CHUNK = CONTAINER_ENV_VAR_MAX_BYTES - 1_000;

/**
 * Most chunks container/unpack_tenant_files.py accepts (it ignores a bundle
 * with more parts, so a larger bundle would start with no files at all).
 */
export const TENANT_FILES_MAX_PARTS = 64;

/** Ceiling on the base64 bundle (and so on what one cold start carries). */
export const TENANT_FILES_MAX_B64 = TENANT_FILES_CHUNK * TENANT_FILES_MAX_PARTS;

const B64 = /^[A-Za-z0-9+/]+={0,2}$/;

/** Minimal KV read surface (lets tests pass a fake). */
export interface TenantFilesStore {
  get(key: string): Promise<string | null>;
}

/** Project a raw KV value into the container env, or `{}` when unusable. */
export function tenantFilesEnv(raw: string | null | undefined): Record<string, string> {
  if (typeof raw !== "string" || raw.trim() === "") return {};
  let doc: unknown;
  try {
    doc = JSON.parse(raw);
  } catch {
    console.warn(`[tenant-files] ${TENANT_FILES_KEY} is not JSON; ignoring it`);
    return {};
  }
  if (typeof doc !== "object" || doc === null || Array.isArray(doc)) return {};
  const { v, bundle } = doc as { v?: unknown; bundle?: unknown };
  if (v !== 1 || typeof bundle !== "string") {
    console.warn(`[tenant-files] ${TENANT_FILES_KEY} has an unknown shape; ignoring it`);
    return {};
  }
  if (bundle.length === 0 || bundle.length > TENANT_FILES_MAX_B64 || !B64.test(bundle)) {
    console.warn(`[tenant-files] ${TENANT_FILES_KEY} bundle is empty, too large or not base64`);
    return {};
  }
  const out: Record<string, string> = {};
  let n = 0;
  for (let i = 0; i < bundle.length; i += TENANT_FILES_CHUNK, n += 1) {
    out[`DIGI_TENANT_FILES_${n}`] = bundle.slice(i, i + TENANT_FILES_CHUNK);
  }
  out.DIGI_TENANT_FILES_PARTS = String(n);
  out.DIGIGRAPH_WEB_SEARCH_SITES_DIR = `${TENANT_FILES_ROOT}/sites`;
  out.DIGISEARCH_PAGE_CORPUS_DIR = `${TENANT_FILES_ROOT}/pages`;
  return out;
}

/** Read the bundle from KV; any failure is "no files" (see FAIL CLOSED). */
export async function readTenantFilesEnv(
  store: TenantFilesStore | undefined,
): Promise<Record<string, string>> {
  if (!store) return {};
  try {
    return tenantFilesEnv(await store.get(TENANT_FILES_KEY));
  } catch (err) {
    console.warn(`[tenant-files] KV read failed: ${err instanceof Error ? err.message : "error"}`);
    return {};
  }
}

/** Env keys this module owns: the chunks, the part count and the two reader dirs. */
export function isTenantFilesEnvKey(key: string): boolean {
  return (
    /^DIGI_TENANT_FILES_(\d+|PARTS)$/.test(key) ||
    key === "DIGIGRAPH_WEB_SEARCH_SITES_DIR" ||
    key === "DIGISEARCH_PAGE_CORPUS_DIR"
  );
}

/**
 * Replace (not merge) the tenant-files env on a container's env vars.
 *
 * The Durable Object keeps `envVars` across cold starts, so a plain merge
 * would keep stale chunks after the KV bundle shrinks or is removed (an old
 * `DIGI_TENANT_FILES_2` beside a new 2-part bundle, or the dirs of a deleted
 * bundle). Every key this module owns is dropped first, then the fresh env is
 * applied; nothing else on `target` is touched.
 */
export function applyTenantFilesEnv(
  target: Record<string, string>,
  fresh: Record<string, string>,
): Record<string, string> {
  for (const key of Object.keys(target)) {
    if (isTenantFilesEnvKey(key)) delete target[key];
  }
  return Object.assign(target, fresh);
}
