import type { Embedder, PageFetcher, TicketSource, VectorStore } from "./sync";
import { EMBED_DIMENSIONS, EMBED_MODEL_ID } from "./model";
import type { TicketArticle, TicketRecord, VectorRecord } from "./vectors";

type FetchFn = typeof fetch;

function statusError(kind: string, status: number): Error {
  return new Error(`${kind}_http_${status}`);
}

function authorizationHeader(raw: string): string {
  const value = raw.trim();
  if (!value) throw new Error("zammad_token_missing");
  if (value.toLowerCase().startsWith("token token=")) return value;
  return `Token token=${value}`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function searchRows(body: unknown): TicketRecord[] {
  let rows: unknown = body;
  const record = asRecord(body);
  if (record) {
    rows = record.tickets ?? record.records ?? record.objects;
  }
  if (!Array.isArray(rows)) throw new Error("zammad_payload");
  return rows.filter((row): row is TicketRecord => {
    const item = asRecord(row);
    return item !== null && typeof item.id === "number";
  });
}

function articleRows(body: unknown): TicketArticle[] {
  let rows: unknown = body;
  const record = asRecord(body);
  if (record && Array.isArray(record.articles)) rows = record.articles;
  if (!Array.isArray(rows)) throw new Error("zammad_payload");
  return rows.filter((row): row is TicketArticle => {
    const item = asRecord(row);
    return item !== null && typeof item.id === "number";
  });
}

export function createTicketSource(readToken: () => string, fetchImpl: FetchFn = fetch): TicketSource {
  async function getJson(url: string): Promise<unknown> {
    const response = await fetchImpl(url, {
      headers: { Authorization: authorizationHeader(readToken()), Accept: "application/json" },
    });
    if (!response.ok) throw statusError("zammad", response.status);
    return response.json();
  }

  return {
    async search(baseUrl, query, page) {
      const url = `${baseUrl}/api/v1/tickets/search?query=${encodeURIComponent(query)}&page=${page}&per_page=50&sort_by=updated_at&order_by=asc&expand=true`;
      return searchRows(await getJson(url));
    },
    async articles(baseUrl, ticketId) {
      return articleRows(await getJson(`${baseUrl}/api/v1/ticket_articles/by_ticket/${ticketId}`));
    },
    async listIds(baseUrl, page) {
      const url = `${baseUrl}/api/v1/tickets/search?query=${encodeURIComponent("id:>0")}&page=${page}&per_page=50&expand=true`;
      return searchRows(await getJson(url)).map((row) => String(row.id));
    },
  };
}

function multipartNdjson(ndjson: string): { body: string; contentType: string } {
  const boundary = `----corpus${crypto.randomUUID().replace(/-/g, "")}`;
  const body = [
    `--${boundary}`,
    'Content-Disposition: form-data; name="vectors"; filename="vectors.ndjson"',
    "Content-Type: application/x-ndjson",
    "",
    ndjson,
    `--${boundary}--`,
    "",
  ].join("\r\n");
  return { body, contentType: `multipart/form-data; boundary=${boundary}` };
}

export function createVectorStore(
  accountId: string,
  readToken: () => string,
  fetchImpl: FetchFn = fetch,
): VectorStore {
  async function post(index: string, action: string, body: string, contentType: string): Promise<void> {
    const token = readToken();
    if (!accountId || !token) throw new Error("vectorize_unconfigured");
    const response = await fetchImpl(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/vectorize/v2/indexes/${index}/${action}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": contentType },
        body,
      },
    );
    if (!response.ok) throw statusError("vectorize", response.status);
  }

  return {
    async upsert(index, vectors) {
      if (vectors.length === 0) return;
      const ndjson = vectors
        .map((vector) => JSON.stringify({ id: vector.id, values: vector.values, metadata: vector.metadata }))
        .join("\n");
      const packed = multipartNdjson(ndjson);
      await post(index, "upsert", packed.body, packed.contentType);
    },
    async deleteIds(index, ids) {
      if (ids.length === 0) return;
      await post(index, "delete_by_ids", JSON.stringify({ ids }), "application/json");
    },
  };
}

type AiBinding = {
  run(model: string, input: { text: string[] }): Promise<{ data?: number[][] }>;
};

export function createEmbedder(ai: AiBinding): Embedder {
  return {
    async embed(texts) {
      const out: number[][] = [];
      for (let offset = 0; offset < texts.length; offset += 16) {
        const batch = texts.slice(offset, offset + 16);
        const result = await ai.run(EMBED_MODEL_ID, { text: batch });
        const data = result.data;
        if (!data || data.length !== batch.length) throw new Error("embed_count");
        for (const row of data) {
          if (row.length !== EMBED_DIMENSIONS) throw new Error("embed_dimensions");
          out.push(row);
        }
      }
      return out;
    },
  };
}

export function createPageFetcher(fetchImpl: FetchFn = fetch): PageFetcher {
  return {
    async fetchText(url) {
      const response = await fetchImpl(url);
      return {
        ok: response.ok,
        status: response.status,
        contentType: response.headers.get("content-type") ?? "",
        body: await response.text(),
      };
    },
  };
}

export type { VectorRecord };
