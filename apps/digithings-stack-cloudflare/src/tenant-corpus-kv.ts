/**
 * Client tenants' corpus map entries from the `TENANT_CONFIG` KV namespace,
 * read at container cold start and merged over the env corpus map.
 *
 * Tenant config is owned by each client repo and written to KV by its deploy,
 * so a new or changed client entry needs no Worker deploy and no secret. The
 * env pair (`DIGI_TENANT_CORPUS_MAP` [vars] for the house entry, the
 * `DIGI_TENANT_CORPUS_MAP_PRIVATE` secret for any legacy client entries) stays
 * the base; this key only adds or replaces client entries:
 *
 *   KV `DIGI_TENANT_CORPUS_MAP` = `{ "<slug>": { ...corpus entry... }, ... }`
 *
 * Every entry passes through as written (web search pins, host cap, page
 * corpus, research prompt, session lock and any other field), so fence
 * semantics are decided by the container's validation, exactly as for env
 * entries.
 *
 * PRECEDENCE, one rule per pair:
 * - house env entry > everything: a KV entry can never shadow or widen it
 *   (`composeCorpusMap` keeps the primary half on a slug collision). Slugs are
 *   compared trimmed and lower-cased, as every consumer reads them, so a KV
 *   slug such as `DIGITHINGS` or ` digithings-ai` is dropped with a warning,
 *   and so is every KV slug in a group that collides once normalised;
 * - KV entry > `DIGI_TENANT_CORPUS_MAP_PRIVATE` entry for the same slug: the
 *   client repo is the source of its own tenant config.
 *
 * FAIL CLOSED to the env map: an absent or blank key, a KV error, malformed
 * JSON, a non-object, no usable entries or an oversized value all yield the
 * env-only map, byte-identical to a stack without this key. Unusable values
 * log one warning; nothing here throws.
 */

import {
  CORPUS_MAP_PRIVATE_ENV_VAR,
  composeCorpusMap,
  parseCorpusMapJson,
  sanitizeClientCorpusMap,
} from "./tenant-config";

/** KV key (in the `TENANT_CONFIG` namespace) holding client corpus map entries. */
export const TENANT_CORPUS_MAP_KEY = "DIGI_TENANT_CORPUS_MAP";

/**
 * Ceiling on the KV value. The composed map travels as one container env
 * string, which must stay well under Linux's 128 KiB per-string execve limit.
 */
export const TENANT_CORPUS_MAP_MAX_BYTES = 96_000;

/** Minimal KV read surface (lets tests pass a fake). */
export interface TenantCorpusMapStore {
  get(key: string): Promise<string | null>;
}

/**
 * The env corpus map with the KV entries merged in, as the container's
 * `DIGI_TENANT_CORPUS_MAP` string.
 *
 * With no usable KV value this is exactly `composeCorpusMap(primary, privateRaw)`.
 */
export function composeCorpusMapWithKv(
  primary: string | undefined,
  privateRaw: string | undefined,
  kvRaw: string | null | undefined,
): string {
  const base = () => composeCorpusMap(primary, privateRaw);
  if (typeof kvRaw !== "string" || kvRaw.trim() === "") return base();
  if (new TextEncoder().encode(kvRaw).length > TENANT_CORPUS_MAP_MAX_BYTES) {
    console.warn(
      `[tenant-corpus-kv] ${TENANT_CORPUS_MAP_KEY} is over ${TENANT_CORPUS_MAP_MAX_BYTES} bytes; using the env map only`,
    );
    return base();
  }
  const parsedKv = parseCorpusMapJson(kvRaw);
  // Slugs are trimmed and lower-cased as the consumers do; house look-alikes
  // and case/whitespace collisions are dropped with a warning.
  const fromKv =
    parsedKv === undefined ? undefined : sanitizeClientCorpusMap(parsedKv, TENANT_CORPUS_MAP_KEY);
  if (fromKv === undefined || Object.keys(fromKv).length === 0) {
    console.warn(
      `[tenant-corpus-kv] ${TENANT_CORPUS_MAP_KEY} is not a usable slug-keyed JSON object; using the env map only`,
    );
    return base();
  }
  // An unusable private secret is dropped here exactly as composeCorpusMap
  // would drop it (with its own warning), so the KV entries still apply.
  const fromPrivate =
    typeof privateRaw === "string" && privateRaw.trim() !== ""
      ? parseCorpusMapJson(privateRaw)
      : undefined;
  if (fromPrivate === undefined && typeof privateRaw === "string" && privateRaw.trim() !== "") {
    console.warn(
      `[tenant-config] ${CORPUS_MAP_PRIVATE_ENV_VAR} is not a usable slug-keyed JSON object; ignoring it`,
    );
  }
  // Both halves keyed by normalised slug, so a KV entry replaces the private
  // entry a consumer would treat as the same tenant.
  const merged = {
    ...sanitizeClientCorpusMap(fromPrivate, CORPUS_MAP_PRIVATE_ENV_VAR),
    ...fromKv,
  };
  return composeCorpusMap(primary, JSON.stringify(merged));
}

/** Read the KV value; a missing binding or a KV error is "no value". */
export async function readTenantCorpusMapKv(
  store: TenantCorpusMapStore | undefined,
): Promise<string | null> {
  if (!store) return null;
  try {
    return await store.get(TENANT_CORPUS_MAP_KEY);
  } catch (err) {
    console.warn(
      `[tenant-corpus-kv] KV read failed: ${err instanceof Error ? err.message : "error"}; using the env map only`,
    );
    return null;
  }
}
