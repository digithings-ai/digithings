/**
 * OCC help-docs weekly recrawl (DIG-3576).
 *
 * Worker-native job: crawl `help.online-compliance-center.com` and idempotently
 * upsert into the `occ_help` store keyed by URL + content hash. Vectorize
 * upsert runs only for changed docs; docs gone from source are deleted. A run
 * with unchanged source writes nothing.
 *
 * The D1 + Vectorize bindings are injected as a store interface so this module
 * stays unit-testable with no Cloudflare account. Live wiring waits on the
 * Vectorize-read/write token (prerequisite on the ticket; Chris grants).
 * Freshness alert threshold ~8-9 days (Chris 14 Oct 18:26): alert when the last
 * success is older than 8 days or a run fails.
 */

/** Weekly Monday clock. Must appear in wrangler.toml [triggers] crons. */
export const OCC_HELP_RECRAWL_CRON = "23 7 * * MON";

/** Alert when the last successful run is older than this. */
export const FRESHNESS_ALERT_AFTER_DAYS = 8;

export type CrawledDoc = {
  url: string;
  /** ISO timestamp of the source document (newest-doc metric reads this). */
  updatedAt: string;
  /** Plain-text content used for the hash and the upsert body. */
  text: string;
};

export type StoredDoc = {
  url: string;
  contentHash: string;
};

export type RecrawlStore = {
  list(): Promise<StoredDoc[]> | StoredDoc[];
  upsert(doc: CrawledDoc & { contentHash: string }): Promise<void> | void;
  remove(url: string): Promise<void> | void;
  getState(): Promise<RecrawlState> | RecrawlState;
  putState(state: RecrawlState): Promise<void> | void;
};

export type RecrawlState = {
  lastSuccessAt: string | null;
};

export type FreshnessMetric = {
  lastSuccessAt: string | null;
  newestDocAt: string | null;
  rowsChanged: number;
  rowsTotal: number;
};

export type FreshnessVerdict = {
  alert: boolean;
  reason: string;
};

export type RecrawlResult = {
  upserted: number;
  deleted: number;
  wrote: boolean;
  dryRun: boolean;
  metric: FreshnessMetric;
  freshness: FreshnessVerdict;
};

/**
 * Non-cryptographic content hash (FNV-1a, 32-bit). Change detector only: two
 * texts with different hashes are different; equal hashes skip the Vectorize
 * write. Not a security boundary.
 */
export function hashContent(text: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function diffDocs(
  source: readonly CrawledDoc[],
  stored: readonly StoredDoc[],
): { upserts: CrawledDoc[]; deletes: string[] } {
  const storedByUrl = new Map(stored.map((doc) => [doc.url, doc.contentHash]));
  const sourceUrls = new Set<string>();
  const upserts: CrawledDoc[] = [];
  for (const doc of source) {
    sourceUrls.add(doc.url);
    if (storedByUrl.get(doc.url) !== hashContent(doc.text)) {
      upserts.push(doc);
    }
  }
  const deletes = stored.filter((doc) => !sourceUrls.has(doc.url)).map((doc) => doc.url);
  return { upserts, deletes };
}

export function newestDocAt(source: readonly CrawledDoc[]): string | null {
  let newest: string | null = null;
  for (const doc of source) {
    if (newest === null || doc.updatedAt > newest) {
      newest = doc.updatedAt;
    }
  }
  return newest;
}

export function freshnessAlert(metric: FreshnessMetric, nowMs: number): FreshnessVerdict {
  if (metric.lastSuccessAt === null) {
    return { alert: true, reason: "never_succeeded" };
  }
  const ageMs = nowMs - Date.parse(metric.lastSuccessAt);
  if (Number.isNaN(ageMs)) {
    return { alert: true, reason: "unparseable_last_success" };
  }
  if (ageMs > FRESHNESS_ALERT_AFTER_DAYS * 24 * 60 * 60 * 1000) {
    return { alert: true, reason: "stale_last_success" };
  }
  return { alert: false, reason: "fresh" };
}

export async function runRecrawl(
  source: readonly CrawledDoc[],
  store: RecrawlStore,
  opts: { dryRun?: boolean; nowMs?: number } = {},
): Promise<RecrawlResult> {
  const dryRun = opts.dryRun ?? false;
  const nowMs = opts.nowMs ?? Date.now();
  const stored = await store.list();
  const { upserts, deletes } = diffDocs(source, stored);
  const rowsChanged = upserts.length + deletes.length;
  const wrote = rowsChanged > 0 && !dryRun;
  if (wrote) {
    for (const doc of upserts) {
      await store.upsert({ ...doc, contentHash: hashContent(doc.text) });
    }
    for (const url of deletes) {
      await store.remove(url);
    }
    await store.putState({ lastSuccessAt: new Date(nowMs).toISOString() });
  }
  const state = await store.getState();
  const metric: FreshnessMetric = {
    lastSuccessAt: state.lastSuccessAt,
    newestDocAt: newestDocAt(source),
    rowsChanged,
    rowsTotal: source.length,
  };
  return {
    upserted: upserts.length,
    deleted: deletes.length,
    wrote,
    dryRun,
    metric,
    freshness: freshnessAlert(metric, nowMs),
  };
}
