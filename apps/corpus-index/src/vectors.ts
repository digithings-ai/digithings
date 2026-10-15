import { assertCleanMetadata, maskPii } from "./pii";
import { chunkWords, prepareBody } from "./chunk";
import { EMBED_DIMENSIONS, EMBED_MODEL_ID } from "./model";

export type TicketArticle = {
  id: number;
  body?: string;
  internal?: boolean;
  content_type?: string;
  from?: string;
  subject?: string;
};

export type TicketRecord = {
  id: number;
  title?: string;
  state?: string;
  group?: string;
  created_at?: string;
  updated_at?: string;
  customer?: string;
  customer_name?: string;
  owner?: string;
};

export type VectorRecord = {
  id: string;
  values: number[];
  metadata: Record<string, string | number>;
};

const CONTENT_CAP = 8000;

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function prefix(ticket: TicketRecord, body: string): string {
  const title = maskPii(text(ticket.title));
  const state = maskPii(text(ticket.state)) || "unknown";
  const header = [`Ticket ${ticket.id}`, title, `State: ${state}`, "Language: und"]
    .filter((line) => line.length > 0)
    .join("\n");
  return `${header}\n\n${body}`.trim();
}

export async function buildTicketVectors(
  ticket: TicketRecord,
  articles: TicketArticle[],
  baseUrl: string,
  embed: (texts: string[]) => number[][] | Promise<number[][]>,
  skipInternal = true,
): Promise<VectorRecord[]> {
  const texts: string[] = [];
  const ids: string[] = [];
  const articleIds: number[] = [];
  const chunkIndexes: number[] = [];
  for (const article of articles) {
    if (skipInternal && article.internal === true) continue;
    const body = prepareBody(text(article.body), article.content_type);
    if (!body) continue;
    const chunks = chunkWords(prefix(ticket, body));
    chunks.forEach((chunk, index) => {
      ids.push(`t${ticket.id}-a${article.id}-c${index}`);
      articleIds.push(article.id);
      chunkIndexes.push(index);
      texts.push(chunk);
    });
  }
  if (texts.length === 0) return [];
  const vectors = await embed(texts);
  if (vectors.length !== texts.length) throw new Error("embed_count");
  return texts.map((content, index) => {
    const values = vectors[index];
    if (!values || values.length !== EMBED_DIMENSIONS) throw new Error("embed_dimensions");
    const metadata: Record<string, string | number> = {
      source: "ticket",
      ticket_id: String(ticket.id),
      article_id: String(articleIds[index]),
      state: maskPii(text(ticket.state)),
      group: maskPii(text(ticket.group)),
      created_at: text(ticket.created_at),
      updated_at: text(ticket.updated_at),
      lang: "und",
      url: `${baseUrl}/#ticket/zoom/${ticket.id}`,
      chunk: chunkIndexes[index],
      model: EMBED_MODEL_ID,
      doc_id: `ticket-${ticket.id}`,
      content: content.slice(0, CONTENT_CAP),
    };
    assertCleanMetadata(metadata);
    return { id: ids[index], values, metadata };
  });
}

export async function buildDocVectors(
  url: string,
  body: string,
  embed: (texts: string[]) => number[][] | Promise<number[][]>,
): Promise<VectorRecord[]> {
  const prepared = prepareBody(body);
  const chunks = chunkWords(prepared);
  if (chunks.length === 0) return [];
  const vectors = await embed(chunks);
  return chunks.map((content, index) => {
    const values = vectors[index];
    if (!values || values.length !== EMBED_DIMENSIONS) throw new Error("embed_dimensions");
    const metadata: Record<string, string | number> = {
      source: "doc",
      lang: "und",
      url,
      chunk: index,
      model: EMBED_MODEL_ID,
      doc_id: `doc-${url}`,
      content: content.slice(0, CONTENT_CAP),
    };
    assertCleanMetadata(metadata);
    return { id: `d${hashUrl(url)}-c${index}`, values, metadata };
  });
}

export function hashUrl(url: string): string {
  let hash = 2166136261;
  for (let i = 0; i < url.length; i += 1) {
    hash ^= url.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

export function idsToDrop(known: string[], live: string[]): string[] {
  const still = new Set(live);
  return known.filter((id) => !still.has(id));
}
