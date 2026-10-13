var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/model.ts
var EMBED_MODEL_ID = "@cf/baai/bge-m3";
var EMBED_DIMENSIONS = 1024;
var CURSOR_OVERLAP_MS = 10 * 60 * 1e3;
function overlapCursor(iso, now = Date.now()) {
  const parsed = Date.parse(iso);
  const base = Number.isFinite(parsed) ? parsed : now;
  return new Date(base - CURSOR_OVERLAP_MS).toISOString();
}
__name(overlapCursor, "overlapCursor");
function isWeeklyReconcile(now) {
  return now.getUTCDay() === 0;
}
__name(isWeeklyReconcile, "isWeeklyReconcile");

// src/http.ts
function authorized(request, secret) {
  const header = request.headers.get("Authorization") ?? "";
  const expected = `Bearer ${secret}`;
  if (header.length !== expected.length) return false;
  let mismatch = 0;
  for (let index = 0; index < header.length; index += 1) {
    mismatch |= header.charCodeAt(index) ^ expected.charCodeAt(index);
  }
  return mismatch === 0;
}
__name(authorized, "authorized");
function normalizePath(pathname) {
  if (pathname.length > 1 && pathname.endsWith("/")) return pathname.slice(0, -1);
  return pathname || "/";
}
__name(normalizePath, "normalizePath");
async function handleFetch(request, env, start2) {
  const path = normalizePath(new URL(request.url).pathname);
  if (request.method === "GET" && (path === "/" || path === "/healthz")) {
    return Response.json({ ok: true, service: "corpus-index", dry_run: env.DRY_RUN === "1" });
  }
  if (request.method === "POST" && path === "/run") {
    if (!env.CRON_KICK_SECRET) return new Response("Not Found", { status: 404 });
    if (!authorized(request, env.CRON_KICK_SECRET)) {
      return new Response("Unauthorized", { status: 401 });
    }
    await start2(env, `manual-${Date.now()}`);
    return Response.json({ ok: true, started: true });
  }
  if (request.method === "POST" && path === "/embed") {
    if (!env.EMBED_SECRET) return new Response("Not Found", { status: 404 });
    if (!authorized(request, env.EMBED_SECRET)) {
      return new Response("Unauthorized", { status: 401 });
    }
    let texts;
    try {
      texts = (await request.json()).text;
    } catch {
      return new Response("Bad Request", { status: 400 });
    }
    if (!Array.isArray(texts) || texts.length === 0 || texts.length > 32 || !texts.every((t) => typeof t === "string" && t.length <= 8e3)) {
      return new Response("Bad Request", { status: 400 });
    }
    const out = await env.AI.run(EMBED_MODEL_ID, { text: texts });
    return Response.json({ result: { data: out.data ?? [] } });
  }
  return new Response("Not Found", { status: 404 });
}
__name(handleFetch, "handleFetch");

// src/workflow.ts
import { WorkflowEntrypoint } from "cloudflare:workers";

// src/clients.ts
function statusError(kind, status) {
  return new Error(`${kind}_http_${status}`);
}
__name(statusError, "statusError");
function authorizationHeader(raw) {
  const value = raw.trim();
  if (!value) throw new Error("zammad_token_missing");
  if (value.toLowerCase().startsWith("token token=")) return value;
  return `Token token=${value}`;
}
__name(authorizationHeader, "authorizationHeader");
function asRecord(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value;
}
__name(asRecord, "asRecord");
function searchRows(body) {
  let rows = body;
  const record = asRecord(body);
  if (record) {
    rows = record.tickets ?? record.records ?? record.objects;
  }
  if (!Array.isArray(rows)) throw new Error("zammad_payload");
  return rows.filter((row) => {
    const item = asRecord(row);
    return item !== null && typeof item.id === "number";
  });
}
__name(searchRows, "searchRows");
function articleRows(body) {
  let rows = body;
  const record = asRecord(body);
  if (record && Array.isArray(record.articles)) rows = record.articles;
  if (!Array.isArray(rows)) throw new Error("zammad_payload");
  return rows.filter((row) => {
    const item = asRecord(row);
    return item !== null && typeof item.id === "number";
  });
}
__name(articleRows, "articleRows");
function createTicketSource(readToken, fetchImpl = fetch) {
  async function getJson(url) {
    const response = await fetchImpl(url, {
      headers: { Authorization: authorizationHeader(readToken()), Accept: "application/json" }
    });
    if (!response.ok) throw statusError("zammad", response.status);
    return response.json();
  }
  __name(getJson, "getJson");
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
    }
  };
}
__name(createTicketSource, "createTicketSource");
function multipartNdjson(ndjson) {
  const boundary = `----corpus${crypto.randomUUID().replace(/-/g, "")}`;
  const body = [
    `--${boundary}`,
    'Content-Disposition: form-data; name="vectors"; filename="vectors.ndjson"',
    "Content-Type: application/x-ndjson",
    "",
    ndjson,
    `--${boundary}--`,
    ""
  ].join("\r\n");
  return { body, contentType: `multipart/form-data; boundary=${boundary}` };
}
__name(multipartNdjson, "multipartNdjson");
function createVectorStore(accountId, readToken, fetchImpl = fetch) {
  async function post(index, action, body, contentType) {
    const token = readToken();
    if (!accountId || !token) throw new Error("vectorize_unconfigured");
    const response = await fetchImpl(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/vectorize/v2/indexes/${index}/${action}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": contentType },
        body
      }
    );
    if (!response.ok) throw statusError("vectorize", response.status);
  }
  __name(post, "post");
  return {
    async upsert(index, vectors) {
      if (vectors.length === 0) return;
      const ndjson = vectors.map((vector) => JSON.stringify({ id: vector.id, values: vector.values, metadata: vector.metadata })).join("\n");
      const packed = multipartNdjson(ndjson);
      await post(index, "upsert", packed.body, packed.contentType);
    },
    async deleteIds(index, ids) {
      if (ids.length === 0) return;
      await post(index, "delete_by_ids", JSON.stringify({ ids }), "application/json");
    }
  };
}
__name(createVectorStore, "createVectorStore");
function createEmbedder(ai) {
  return {
    async embed(texts) {
      const out = [];
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
    }
  };
}
__name(createEmbedder, "createEmbedder");
function createPageFetcher(fetchImpl = fetch) {
  return {
    async fetchText(url) {
      const response = await fetchImpl(url);
      return {
        ok: response.ok,
        status: response.status,
        contentType: response.headers.get("content-type") ?? "",
        body: await response.text()
      };
    }
  };
}
__name(createPageFetcher, "createPageFetcher");

// src/config.ts
var ID = /^[a-z0-9][a-z0-9-]{0,62}$/;
var INDEX = /^[a-z0-9][a-z0-9-]{0,62}$/;
function httpsUrl(value, field) {
  if (typeof value !== "string") throw new Error(`config_${field}`);
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`config_${field}`);
  }
  if (url.protocol !== "https:") throw new Error(`config_${field}`);
  if (url.username || url.password) throw new Error(`config_${field}`);
  return url.origin;
}
__name(httpsUrl, "httpsUrl");
function slug(value, field, pattern) {
  if (typeof value !== "string" || !pattern.test(value)) throw new Error(`config_${field}`);
  return value;
}
__name(slug, "slug");
function parseJob(raw) {
  if (typeof raw !== "object" || raw === null) throw new Error("config_job");
  const record = raw;
  if ("token" in record || "apiToken" in record || "secret" in record) {
    throw new Error("config_secret");
  }
  return {
    id: slug(record.id, "id", ID),
    zammadBaseUrl: httpsUrl(record.zammadBaseUrl, "zammadBaseUrl"),
    siteUrl: httpsUrl(record.siteUrl, "siteUrl"),
    helpIndex: slug(record.helpIndex, "helpIndex", INDEX),
    ticketsIndex: slug(record.ticketsIndex, "ticketsIndex", INDEX),
    skipInternal: record.skipInternal !== false
  };
}
__name(parseJob, "parseJob");
function parseJobs(raw) {
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("config_jobs");
  }
  if (!Array.isArray(parsed)) throw new Error("config_jobs");
  return parsed.map(parseJob);
}
__name(parseJobs, "parseJobs");
var JOBS_KEY = "corpus-index:jobs";

// src/pii.ts
var EMAIL = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
var IBAN = /\b[A-Z]{2}\d{2}(?:\s*[A-Z0-9]){11,30}\b/gi;
var PHONE = /(?:\+\d{1,3}|00\d{1,3})(?:[\s().-]*\d){7,14}\b|\(\d{2,5}\)[\s.-]*\d{3,4}[\s.-]*\d{3,4}\b/g;
var IDENTITY_LINE = /^(?:from|customer|owner|sender|name|contact|email|e-mail|phone|tel|mobile|iban)\s*:.*$/i;
var METADATA_KEYS = [
  "source",
  "ticket_id",
  "article_id",
  "state",
  "group",
  "created_at",
  "updated_at",
  "lang",
  "url",
  "chunk",
  "model",
  "doc_id",
  "content"
];
var ALLOWED = new Set(METADATA_KEYS);
var FORBIDDEN_KEY = /email|phone|name|customer|from|sender|owner|iban|author/i;
function containsRawIdentity(value) {
  EMAIL.lastIndex = 0;
  IBAN.lastIndex = 0;
  PHONE.lastIndex = 0;
  return EMAIL.test(value) || IBAN.test(value) || PHONE.test(value);
}
__name(containsRawIdentity, "containsRawIdentity");
var W = "[A-Z\xC4\xD6\xDC][\\p{L}'\u2019.-]+";
var NAME_RUN = `${W}(?:\\s+(?:von|van|de|zu)?\\s*${W}){0,2}`;
var MAIL_HEADER = new RegExp(
  `\\b(Von|From|An|To|Cc|Bcc|Reply-To|Antwort an)\\s*:\\s*[^\\n]*?(?=\\s(?:Von|From|An|To|Cc|Bcc|Gesendet|Sent|Datum|Date|Betreff|Subject)\\s*:|\\n|$)`,
  "gu"
);
var GREETING = new RegExp(
  `\\b(Hallo|Hi|Hello|Hey|Dear|Moin|Servus|Liebe[rs]?|Sehr geehrte[rs]?|Guten (?:Tag|Morgen|Abend))(\\s+(?:Frau|Herr|Hr\\.|Fr\\.|Mr\\.?|Mrs\\.?|Ms\\.?|Dr\\.))*\\s+(${NAME_RUN})`,
  "gu"
);
var CLOSING = new RegExp(
  `\\b(Gr\xFC\xDFen|Gr\xFC\xDFe|Gru\xDF|Gruss|Gr\xFCsse|regards|Regards|Cheers)([,!.]?)\\s+(${NAME_RUN})`,
  "gu"
);
var HONORIFIC = new RegExp(`\\b(Frau|Herr|Herrn|Hr\\.|Fr\\.|Mr\\.?|Mrs\\.?|Ms\\.?|Dr\\.)\\s+(${NAME_RUN})`, "gu");
var COMPANY = new RegExp(
  `(?:${W}\\s+){0,4}${W}\\s+(?:gGmbH|GmbH(?:\\s*&\\s*Co\\.?\\s*KG)?|AG|KG|e\\.\\s?V\\.|UG|mbH|Ltd\\.?|Inc\\.?|LLC|SE|eG)\\b`,
  "gu"
);
var NOT_NAMES = /* @__PURE__ */ new Set(["Team", "Support", "Ihr", "Ihre", "Euer", "Eure", "Zusammen", "Alle", "Allerseits", "OCC", "Online", "Compliance", "Center"]);
function escapeRe(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
__name(escapeRe, "escapeRe");
function namesFrom(values) {
  const out = /* @__PURE__ */ new Set();
  for (const value of values) {
    if (typeof value !== "string") continue;
    for (const part of value.split(/[,;]/)) {
      const name = part.replace(/<[^>]*>/g, "").replace(/["']/g, "").replace(EMAIL, "").trim();
      if (name.length < 3 || /^[\d\W]+$/.test(name)) continue;
      out.add(name);
      for (const token of name.split(/\s+/)) if (token.length >= 3 && /^\p{Lu}/u.test(token)) out.add(token);
    }
  }
  return [...out].sort((a, b) => b.length - a.length);
}
__name(namesFrom, "namesFrom");
function maskPii(text2, names = []) {
  const lines = text2.split("\n").filter((line) => !IDENTITY_LINE.test(line.trim()));
  let out = lines.join("\n").replace(EMAIL, "[email]").replace(IBAN, "[iban]").replace(PHONE, "[phone]").replace(MAIL_HEADER, (_m, key) => `${key}: [name]`);
  for (const name of names) {
    out = out.replace(new RegExp(`(?<![\\p{L}])${escapeRe(name)}(?![\\p{L}])`, "gu"), "[name]");
  }
  const keep = /* @__PURE__ */ __name((lead, run) => {
    const first = run.split(/\s+/)[0] ?? "";
    return NOT_NAMES.has(first) ? `${lead}${run}` : `${lead}[name]`;
  }, "keep");
  return out.replace(GREETING, (_m, g, h = "", run) => keep(`${g}${h ?? ""} `, run)).replace(CLOSING, (_m, c, p, run) => keep(`${c}${p} `, run)).replace(HONORIFIC, (_m, h, run) => keep(`${h} `, run)).replace(COMPANY, "[organization]");
}
__name(maskPii, "maskPii");
function assertCleanMetadata(metadata) {
  for (const [key, value] of Object.entries(metadata)) {
    if (!ALLOWED.has(key) || FORBIDDEN_KEY.test(key)) {
      throw new Error("metadata_identity");
    }
    if (typeof value !== "string" && typeof value !== "number") {
      throw new Error("metadata_identity");
    }
    if (typeof value === "string" && containsRawIdentity(value)) {
      throw new Error("metadata_identity");
    }
    if (key === "url" && typeof value === "string" && value.includes("@")) {
      throw new Error("metadata_identity");
    }
  }
}
__name(assertCleanMetadata, "assertCleanMetadata");

// src/chunk.ts
var DEFAULT_SIZE = 500;
var DEFAULT_OVERLAP = 50;
function htmlToText(html) {
  return html.replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<br\s*\/?>/gi, "\n").replace(/<\/p>/gi, "\n").replace(/<[^>]+>/g, " ").replace(/&nbsp;/gi, " ").replace(/&amp;/gi, "&").replace(/&lt;/gi, "<").replace(/&gt;/gi, ">").replace(/&#39;|&apos;/gi, "'").replace(/&quot;/gi, '"').replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}
__name(htmlToText, "htmlToText");
function stripQuotesAndSignature(text2) {
  const kept = [];
  for (const line of text2.split("\n")) {
    const trimmed = line.trim();
    if (trimmed === "--" || trimmed.startsWith("-- ")) break;
    if (trimmed.startsWith(">")) continue;
    if (/^On .+ wrote:\s*$/i.test(trimmed)) continue;
    if (/^Am .+ schrieb.*:\s*$/i.test(trimmed)) continue;
    if (/^Sent from my /i.test(trimmed)) continue;
    kept.push(line);
  }
  return kept.join("\n").trim();
}
__name(stripQuotesAndSignature, "stripQuotesAndSignature");
function chunkWords(text2, size = DEFAULT_SIZE, overlap = DEFAULT_OVERLAP) {
  const words = text2.split(/\s+/).filter((word) => word.length > 0);
  if (words.length === 0) return [];
  if (words.length <= size) return [words.join(" ")];
  const step = Math.max(1, size - overlap);
  const out = [];
  for (let index = 0; index < words.length; index += step) {
    const slice = words.slice(index, index + size);
    if (slice.length === 0) break;
    out.push(slice.join(" "));
    if (index + size >= words.length) break;
  }
  return out;
}
__name(chunkWords, "chunkWords");
function prepareBody(raw, contentType, names = []) {
  const asText = /html/i.test(contentType ?? "") || /<[a-z][\s\S]*>/i.test(raw) ? htmlToText(raw) : raw;
  return maskPii(stripQuotesAndSignature(asText), names);
}
__name(prepareBody, "prepareBody");

// src/vectors.ts
var CONTENT_CAP = 8e3;
function text(value) {
  return typeof value === "string" ? value : "";
}
__name(text, "text");
function prefix(ticket, body, names) {
  const title = maskPii(text(ticket.title), names);
  const state = maskPii(text(ticket.state)) || "unknown";
  const header = [`Ticket ${ticket.id}`, title, `State: ${state}`, "Language: und"].filter((line) => line.length > 0).join("\n");
  return `${header}

${body}`.trim();
}
__name(prefix, "prefix");
async function buildTicketVectors(ticket, articles, baseUrl, embed, skipInternal = true) {
  const texts = [];
  const ids = [];
  const articleIds = [];
  const chunkIndexes = [];
  const names = namesFrom([
    ticket.customer,
    ticket.customer_name,
    ticket.owner,
    ticket.organization,
    ticket.created_by,
    ...articles.flatMap((a) => [a.from, a.to, a.cc, a.created_by])
  ]);
  for (const article of articles) {
    if (skipInternal && article.internal === true) continue;
    const body = prepareBody(text(article.body), article.content_type, names);
    if (!body) continue;
    const chunks = chunkWords(prefix(ticket, body, names));
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
    const metadata = {
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
      content: content.slice(0, CONTENT_CAP)
    };
    assertCleanMetadata(metadata);
    return { id: ids[index], values, metadata };
  });
}
__name(buildTicketVectors, "buildTicketVectors");
async function buildDocVectors(url, body, embed) {
  const prepared = prepareBody(body);
  const chunks = chunkWords(prepared);
  if (chunks.length === 0) return [];
  const vectors = await embed(chunks);
  return chunks.map((content, index) => {
    const values = vectors[index];
    if (!values || values.length !== EMBED_DIMENSIONS) throw new Error("embed_dimensions");
    const metadata = {
      source: "doc",
      lang: "und",
      url,
      chunk: index,
      model: EMBED_MODEL_ID,
      doc_id: `doc-${url}`,
      content: content.slice(0, CONTENT_CAP)
    };
    assertCleanMetadata(metadata);
    return { id: `d${hashUrl(url)}-c${index}`, values, metadata };
  });
}
__name(buildDocVectors, "buildDocVectors");
function hashUrl(url) {
  let hash = 2166136261;
  for (let i = 0; i < url.length; i += 1) {
    hash ^= url.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}
__name(hashUrl, "hashUrl");
function idsToDrop(known, live) {
  const still = new Set(live);
  return known.filter((id) => !still.has(id));
}
__name(idsToDrop, "idsToDrop");

// src/sync.ts
var PAGE = 50;
function cursorKey(jobId) {
  return `corpus-index:cursor:${jobId}:tickets`;
}
__name(cursorKey, "cursorKey");
function ticketIdsKey(jobId) {
  return `corpus-index:ticket-ids:${jobId}`;
}
__name(ticketIdsKey, "ticketIdsKey");
function vectorIdsKey(jobId, ticketId) {
  return `corpus-index:vector-ids:${jobId}:${ticketId}`;
}
__name(vectorIdsKey, "vectorIdsKey");
function docListKey(jobId) {
  return `corpus-index:docs:${jobId}`;
}
__name(docListKey, "docListKey");
function docHashKey(jobId, url) {
  return `corpus-index:doc-hash:${jobId}:${hashUrl(url)}`;
}
__name(docHashKey, "docHashKey");
function docIdsKey(jobId, url) {
  return `corpus-index:doc-ids:${jobId}:${hashUrl(url)}`;
}
__name(docIdsKey, "docIdsKey");
async function readJson(kv, key, fallback) {
  const raw = await kv.get(key);
  if (!raw) return fallback;
  return JSON.parse(raw);
}
__name(readJson, "readJson");
async function contentHash(text2) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text2));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
__name(contentHash, "contentHash");
function sitemapLocs(xml) {
  const locs = [];
  const pattern = /<loc>\s*([^<]+)\s*<\/loc>/gi;
  let match = pattern.exec(xml);
  while (match) {
    locs.push(match[1].trim());
    match = pattern.exec(xml);
  }
  return locs;
}
__name(sitemapLocs, "sitemapLocs");
async function loadJobs(kv) {
  const raw = await kv.get(JOBS_KEY);
  if (!raw) return [];
  return parseJobs(raw);
}
__name(loadJobs, "loadJobs");
async function syncTickets(job, kv, source, store, embedder, now, dryRun) {
  const stored = await kv.get(cursorKey(job.id));
  const query = `updated_at:[${stored ? overlapCursor(stored, now.getTime()) : "1970-01-01T00:00:00.000Z"} TO *]`;
  let page = 1;
  let tickets = 0;
  let written = 0;
  let newest = stored ?? "";
  const seen = new Set(await readJson(kv, ticketIdsKey(job.id), []));
  const embedTexts = /* @__PURE__ */ __name((texts) => dryRun ? Promise.resolve(texts.map(() => Array.from({ length: EMBED_DIMENSIONS }, () => 0))) : embedder.embed(texts), "embedTexts");
  while (page < 1e3) {
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
        job.skipInternal
      );
      const previous = await readJson(kv, vectorIdsKey(job.id, ticketId), []);
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
    const live = [];
    let idPage = 1;
    while (idPage < 1e3) {
      const ids = await source.listIds(job.zammadBaseUrl, idPage);
      if (ids.length === 0) break;
      live.push(...ids);
      if (ids.length < PAGE) break;
      idPage += 1;
    }
    const known = await readJson(kv, ticketIdsKey(job.id), []);
    for (const id of idsToDrop(known, live)) {
      const vids = await readJson(kv, vectorIdsKey(job.id, id), []);
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
__name(syncTickets, "syncTickets");
async function syncDocs(job, kv, pages, store, embedder, dryRun) {
  const root = await pages.fetchText(`${job.siteUrl}/sitemap.xml`);
  if (!root.ok) throw new Error(`sitemap_http_${root.status}`);
  const locs = sitemapLocs(root.body);
  const pageUrls = locs.filter((loc) => !loc.endsWith(".xml"));
  for (const loc of locs.filter((item) => item.endsWith(".xml"))) {
    const child = await pages.fetchText(loc);
    if (!child.ok) continue;
    pageUrls.push(...sitemapLocs(child.body).filter((item) => !item.endsWith(".xml")));
  }
  const previous = await readJson(kv, docListKey(job.id), []);
  const embedTexts = /* @__PURE__ */ __name((texts) => dryRun ? Promise.resolve(texts.map(() => Array.from({ length: EMBED_DIMENSIONS }, () => 0))) : embedder.embed(texts), "embedTexts");
  const live = [];
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
    if (await kv.get(docHashKey(job.id, url)) === hash) continue;
    const built = await buildDocVectors(url, page.body, embedTexts);
    if (!dryRun) {
      const priorIds = await readJson(kv, docIdsKey(job.id, url), []);
      if (priorIds.length > 0) await store.deleteIds(job.helpIndex, priorIds);
      if (built.length > 0) await store.upsert(job.helpIndex, built);
      await kv.put(docHashKey(job.id, url), hash);
      await kv.put(docIdsKey(job.id, url), JSON.stringify(built.map((vector) => vector.id)));
    }
    docs += built.length;
  }
  let deleted = 0;
  for (const url of idsToDrop(previous, live)) {
    const ids = await readJson(kv, docIdsKey(job.id, url), []);
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
__name(syncDocs, "syncDocs");

// src/run.ts
async function runIndex(env, now = /* @__PURE__ */ new Date()) {
  const jobs = await loadJobs(env.CORPUS_INDEX_KV);
  const counts = { jobs: jobs.length, tickets: 0, vectors: 0, docs: 0, deleted: 0, skipped: 0 };
  if (jobs.length === 0) {
    console.log(JSON.stringify({ event: "no_jobs" }));
    return counts;
  }
  const dryRun = env.DRY_RUN === "1";
  const source = createTicketSource(() => env.ZAMMAD_API_TOKEN ?? "");
  const store = createVectorStore(env.CLOUDFLARE_ACCOUNT_ID ?? "", () => env.CLOUDFLARE_API_TOKEN ?? "");
  const embedder = createEmbedder(env.AI);
  const pages = createPageFetcher();
  for (const job of jobs) {
    const tickets = await syncTickets(job, env.CORPUS_INDEX_KV, source, store, embedder, now, dryRun);
    const docs = await syncDocs(job, env.CORPUS_INDEX_KV, pages, store, embedder, dryRun);
    counts.tickets += tickets.tickets;
    counts.vectors += tickets.vectors;
    counts.deleted += tickets.deleted + docs.deleted;
    counts.docs += docs.docs;
    counts.skipped += docs.skipped;
    console.log(
      JSON.stringify({
        event: "corpus_index_job",
        job: job.id,
        tickets: tickets.tickets,
        vectors: tickets.vectors,
        docs: docs.docs,
        deleted: tickets.deleted + docs.deleted,
        skipped: docs.skipped,
        dry_run: dryRun
      })
    );
  }
  return counts;
}
__name(runIndex, "runIndex");

// src/workflow.ts
var CorpusIndexWorkflow = class extends WorkflowEntrypoint {
  static {
    __name(this, "CorpusIndexWorkflow");
  }
  async run(_event, step) {
    return step.do("index", async () => {
      const counts = await runIndex(this.env);
      return { jobs: counts.jobs, tickets: counts.tickets, vectors: counts.vectors, docs: counts.docs };
    });
  }
};

// src/index.ts
async function start(env, instanceId) {
  try {
    await env.CORPUS_INDEX_WORKFLOW.create({ id: instanceId });
  } catch (err) {
    const message = err instanceof Error ? err.message : "";
    if (!/already/i.test(message)) throw err;
    console.log(JSON.stringify({ event: "already_running", instance: instanceId }));
  }
}
__name(start, "start");
var index_default = {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(start(env, `cron-${controller.scheduledTime}`));
  },
  async fetch(request, env) {
    return handleFetch(request, env, start);
  }
};
export {
  CorpusIndexWorkflow,
  index_default as default
};
//# sourceMappingURL=index.js.map
