import { JOBS_KEY, parseJobs, type CorpusJob } from "./config";
import { EMBED_DIMENSIONS, isWeeklyReconcile, overlapCursor } from "./model";
import {
  buildDocVectors,
  buildTicketVectors,
  hashUrl,
  idsToDrop,
  type TicketArticle,
  type TicketRecord,
  type VectorRecord,
} from "./vectors";

export type KvStore = {
  get(key: string): Promise<string | null>;
  put(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
};

export type TicketSource = {
  search(baseUrl: string, query: string, page: number): Promise<TicketRecord[]>;
  articles(baseUrl: string, ticketId: number): Promise<TicketArticle[]>;
  listIds(baseUrl: string, page: number): Promise<string[]>;
};

export type VectorStore = {
  upsert(index: string, vectors: VectorRecord[]): Promise<void>;
  deleteIds(index: string, ids: string[]): Promise<void>;
};

export type Embedder = {
  embed(texts: string[]): Promise<number[][]>;
};

export type PageFetcher = {
  fetchText(url: string): Promise<{ ok: boolean; status: number; contentType: string; body: string }>;
};

const PAGE = 50;

function cursorKey(jobId: string): string {
  return `corpus-index:cursor:${jobId}:tickets`;
}

function ticketIdsKey(jobId: string): string {
  return `corpus-index:ticket-ids:${jobId}`;
}

function vectorIdsKey(jobId: string, ticketId: string): string {
  return `corpus-index:vector-ids:${jobId}:${ticketId}`;
}

function docListKey(jobId: string): string {
  return `corpus-index:docs:${jobId}`;
}

function docHashKey(jobId: string, url: string): string {
  return `corpus-index:doc-hash:${jobId}:${hashUrl(url)}`;
}

function docIdsKey(jobId: string, url: string): string {
  return `corpus-index:doc-ids:${jobId}:${hashUrl(url)}`;
}

async function readJson<T>(kv: KvStore, key: string, fallback: T): Promise<T> {
  const raw = await kv.get(key);
  if (!raw) return fallback;
  return JSON.parse(raw) as T;
}

export async function contentHash(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function sitemapLocs(xml: string): string[] {
  const locs: string[] = [];
  const pattern = /<loc>\s*([^<]+)\s*<\/loc>/gi;
  let match: RegExpExecArray | null = pattern.exec(xml);
  while (match) {
    locs.push(match[1].trim());
    match = pattern.exec(xml);
  }
  return locs;
}

export async function loadJobs(kv: KvStore): Promise<CorpusJob[]> {
  const raw = await kv.get(JOBS_KEY);
  if (!raw) return [];
  return parseJobs(raw);
}

export async function syncTickets(
  job: CorpusJob,
  kv: KvStore,
  source: TicketSource,
  store: VectorStore,
  embedder: Embedder,
  now: Date,
  dryRun: boolean,
): Promise<{ tickets: number; vectors: number; deleted: number }> {
  const stored = await kv.get(cursorKey(job.id));
  const query = stored
    ? `updated_at:>=${overlapCursor(stored, now.getTime())}`
    : "updated_at:>=1970-01-01T00:00:00.000Z";
  let page = 1;
  let tickets = 0;
  let written = 0;
  let newest = stored ?? "";
  const seen = new Set(await readJson<string[]>(kv, ticketIdsKey(job.id), []));
  const embedTexts = (texts: string[]) =>
    dryRun
      ? Promise.resolve(texts.map(() => Array.from({ length: EMBED_DIMENSIONS }, () => 0)))
      : embedder.embed(texts);

  while (page < 1000) {
    const batch = await source.search(job.zammadBaseUrl, query, page);
    if (batch.length === 0) break;
    for (const ticket of batch) {
      tickets += 1;
      const ticketId = String(ticket.id);
      seen.add(ticketId);
      if ((ticket.updated_at ?? "") > newest) newest = ticket.updated_at ?? newest;
      const articles = await source.articles(job.zammadBaseUrl, ticket.id);
      const built = await buildTicketVectors(
        ticket,
        articles,
        job.zammadBaseUrl,
        embedTexts,
        job.skipInternal,
      );
      const previous = await readJson<string[]>(kv, vectorIdsKey(job.id, ticketId), []);
      const nextIds = built.map((vector) => vector.id);
      if (!dryRun) {
        if (previous.length > 0) await store.deleteIds(job.ticketsIndex, previous);
        if (built.length > 0) await store.upsert(job.ticketsIndex, built);
        await kv.put(vectorIdsKey(job.id, ticketId), JSON.stringify(nextIds));
      }
      written += built.length;
    }
    if (batch.length < PAGE) break;
    page += 1;
  }

  let deleted = 0;
  if (isWeeklyReconcile(now)) {
    const live: string[] = [];
    let idPage = 1;
    while (idPage < 1000) {
      const ids = await source.listIds(job.zammadBaseUrl, idPage);
      if (ids.length === 0) break;
      live.push(...ids);
      if (ids.length < PAGE) break;
      idPage += 1;
    }
    const known = await readJson<string[]>(kv, ticketIdsKey(job.id), []);
    for (const id of idsToDrop(known, live)) {
      const vids = await readJson<string[]>(kv, vectorIdsKey(job.id, id), []);
      if (!dryRun && vids.length > 0) await store.deleteIds(job.ticketsIndex, vids);
      if (!dryRun) await kv.delete(vectorIdsKey(job.id, id));
      deleted += vids.length;
    }
    if (!dryRun) await kv.put(ticketIdsKey(job.id), JSON.stringify(live));
  } else if (!dryRun) {
    await kv.put(ticketIdsKey(job.id), JSON.stringify([...seen]));
  }

  if (!dryRun && newest) await kv.put(cursorKey(job.id), newest);
  return { tickets, vectors: written, deleted };
}

export async function syncDocs(
  job: CorpusJob,
  kv: KvStore,
  pages: PageFetcher,
  store: VectorStore,
  embedder: Embedder,
  dryRun: boolean,
): Promise<{ docs: number; deleted: number; skipped: number }> {
  const root = await pages.fetchText(`${job.siteUrl}/sitemap.xml`);
  if (!root.ok) throw new Error(`sitemap_http_${root.status}`);
  const locs = sitemapLocs(root.body);
  const pageUrls = locs.filter((loc) => !loc.endsWith(".xml"));
  for (const loc of locs.filter((item) => item.endsWith(".xml"))) {
    const child = await pages.fetchText(loc);
    if (!child.ok) continue;
    pageUrls.push(...sitemapLocs(child.body).filter((item) => !item.endsWith(".xml")));
  }

  const previous = await readJson<string[]>(kv, docListKey(job.id), []);
  const embedTexts = (texts: string[]) =>
    dryRun
      ? Promise.resolve(texts.map(() => Array.from({ length: EMBED_DIMENSIONS }, () => 0)))
      : embedder.embed(texts);
  const live: string[] = [];
  let docs = 0;
  let skipped = 0;
  for (const url of pageUrls) {
    const page = await pages.fetchText(url);
    if (!page.ok) continue;
    if (page.contentType.includes("pdf") || url.toLowerCase().endsWith(".pdf")) {
      skipped += 1;
      continue;
    }
    live.push(url);
    const hash = await contentHash(page.body);
    if ((await kv.get(docHashKey(job.id, url))) === hash) continue;
    const built = await buildDocVectors(url, page.body, embedTexts);
    if (!dryRun) {
      const priorIds = await readJson<string[]>(kv, docIdsKey(job.id, url), []);
      if (priorIds.length > 0) await store.deleteIds(job.helpIndex, priorIds);
      if (built.length > 0) await store.upsert(job.helpIndex, built);
      await kv.put(docHashKey(job.id, url), hash);
      await kv.put(docIdsKey(job.id, url), JSON.stringify(built.map((vector) => vector.id)));
    }
    docs += built.length;
  }

  let deleted = 0;
  for (const url of idsToDrop(previous, live)) {
    const ids = await readJson<string[]>(kv, docIdsKey(job.id, url), []);
    if (!dryRun && ids.length > 0) await store.deleteIds(job.helpIndex, ids);
    if (!dryRun) {
      await kv.delete(docHashKey(job.id, url));
      await kv.delete(docIdsKey(job.id, url));
    }
    deleted += ids.length;
  }
  if (!dryRun) await kv.put(docListKey(job.id), JSON.stringify(live));
  return { docs, deleted, skipped };
}
