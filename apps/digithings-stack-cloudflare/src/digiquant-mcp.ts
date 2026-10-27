/**
 * Worker-native digiquant market-data MCP (DIG-2913).
 *
 * Replaces the read path that used to run in the dedicated digiquant-mcp
 * container (deleted in DIG-5558; it served FastMCP streamable-http on :8767
 * under Firecracker) with the Worker itself: the tools read the sealed R2
 * generations through the `MARKET_DATA` binding and decode parquet with
 * `hyparquet`, exactly like `src/market-data.ts` already does for
 * `/v1/market/*`. No container hop, no Python process on the read path.
 *
 * Scope of this surface — sealed R2 data only:
 *   - `digiquant_list_market_data`  manifest coverage (tickers, macro series)
 *   - `digiquant_get_price_history` sealed OHLCV window for one ticker
 *   - `digiquant_get_macro_series`   sealed macro window per series id
 *
 * Deliberate differences from `digiquant/src/digiquant/mcp_server.py`:
 *   1. NO live vendor overlap. Python fetches `(seal, as_of]` from the vendor
 *      when `as_of` is after the seal. A Worker cannot run those fetchers, so a
 *      request beyond the seal fails loud (`beyond_seal`) instead of serving a
 *      history-only window that would look fresh. `stale` is therefore the
 *      seal-age gate alone, never a live-fetch flag.
 *   2. NO technical indicators (`digiquant_get_price_technicals`) — computing
 *      the 32-column `TECHNICAL_COLUMNS` set here would be a hand-written
 *      second implementation of `digiquant/data/prices/technicals.py` on a
 *      read path, which is a silent-wrong-number risk. That tool stays on the
 *      Python server until the seal carries precomputed indicators.
 *
 * Protocol: stateless Streamable HTTP at `/mcp` (no session tracking — every
 * tool call re-reads R2 or hits the per-instance 900s cache). The 900s TTL is
 * the same policy as the Python server (`_TTL_SECONDS`, never caching a stale
 * payload); it lives in the Durable Object instance that owns this endpoint,
 * which is why the endpoint is a DO rather than a plain stateless Worker:
 * single-instance cache coherence without a second storage round trip.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { parquetReadObjects } from "hyparquet";
import { z } from "zod";
import { authorizeMcpEdge, type McpEdgeAuthEnv } from "./mcp-edge-auth";
import {
  isoDate,
  manifestTickers,
  resolvePointer,
  shapeCloses,
  type Manifest,
} from "./market-data";

/** Streamable-HTTP endpoint path (matches the Python server's `/mcp`). */
export const DIGIQUANT_MCP_PATH = "/mcp";

export const MANIFEST_KEY = "market-data/manifest.json";

/** Python `_TTL_SECONDS`: 15 minutes, and stale payloads are never cached. */
export const TTL_MS = 900_000;

/** Python `_MAX_LOOKBACK`. */
export const MAX_LOOKBACK = 500;

/** Python `staleness_gate` default bound. */
export const STALE_BOUND_TRADING_DAYS = 5;

const PRICE_OBJECT_PREFIX = "market-data/price/";
const MACRO_OBJECT_PREFIX = "market-data/macro/";

/** Minimal R2 surface the read path needs (a fake implements the same shape). */
export interface R2BodyLike {
  arrayBuffer(): Promise<ArrayBuffer>;
  text(): Promise<string>;
  json(): Promise<unknown>;
}

export interface R2BucketLike {
  get(key: string): Promise<R2BodyLike | null>;
}

/** Injected parquet decoder: `hyparquet` in the Worker, a stub in tests. */
export type ParquetDecode = (
  bytes: ArrayBuffer,
  columns?: readonly string[],
) => Promise<Array<Record<string, unknown>>>;

const defaultDecode: ParquetDecode = async (bytes, columns) =>
  (await parquetReadObjects(
    columns === undefined ? { file: bytes } : { file: bytes, columns: [...columns] },
  )) as Array<Record<string, unknown>>;

export type CacheEntry = { at: number; payload: string };
export type CacheStore = Map<string, CacheEntry>;

export interface ReadDeps {
  bucket: R2BucketLike;
  decode?: ParquetDecode;
  /** Per-instance 900s cache; omitted means no caching. */
  cache?: CacheStore;
  /** Injected clock (tests). */
  now?: () => number;
}

/**
 * Read-path failure with the exact JSON error envelope the Python server emits.
 * `envelope` is the final `{"error": ...}` text, so parity strings
 * (`LookupError: unknown ticker 'XYZ'`) are asserted verbatim.
 */
export class ReadPathError extends Error {
  constructor(
    readonly code: string,
    readonly envelope: string,
  ) {
    super(envelope);
    this.name = "ReadPathError";
  }
}

function errorPayload(text: string): string {
  return JSON.stringify({ error: text });
}

/**
 * Python catches `Exception` and returns `{"error": ...}`. Only a typed
 * `ReadPathError` becomes an envelope here; anything else is a bug in this
 * module and must stay loud (the tool layer turns it into an isError result).
 */
function envelopeError(error: unknown): string {
  if (error instanceof ReadPathError) return errorPayload(error.envelope);
  throw error;
}

function unknownTicker(ticker: string): ReadPathError {
  return new ReadPathError("unknown_ticker", `LookupError: unknown ticker '${ticker}'`);
}

function unknownSeries(seriesId: string): ReadPathError {
  return new ReadPathError("unknown_series", `LookupError: unknown macro series '${seriesId}'`);
}

/** Python `_lookback_error`: reject non-integers and anything < 1, never clamp to 0. */
export function lookbackError(raw: unknown): string | null {
  if (typeof raw === "boolean" || typeof raw !== "number" || !Number.isFinite(raw)) {
    return "lookback must be an integer >= 1";
  }
  if (!Number.isInteger(raw) || raw < 1) {
    return "lookback must be an integer >= 1";
  }
  return null;
}

/** Python `_bounded_lookback`. */
export function boundedLookback(lookback: number): number {
  return Math.min(Math.trunc(lookback), MAX_LOOKBACK);
}

/** Python `normalize_ticker`: uppercase, every `/` becomes `-` (`BRK/B` → `BRK-B`). */
export function normalizeTicker(ticker: string): string {
  return ticker.trim().toUpperCase().replaceAll("/", "-");
}

/** Python `latest_pointer_key`. */
export function pricePointerKey(ticker: string): string {
  return `${PRICE_OBJECT_PREFIX}${normalizeTicker(ticker)}/latest`;
}

/** Python `macro_latest_pointer_key`. */
export function macroPointerKey(source: string, series: string): string {
  return `${MACRO_OBJECT_PREFIX}${source}__${series}/latest`;
}

function toUtcMillis(iso: string): number {
  return Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
}

/** Python `trading_days_between` without a calendar: counts Mon–Fri in `(start, end]`. */
export function tradingDaysBetween(start: string, end: string): number {
  const startMs = toUtcMillis(start);
  const endMs = toUtcMillis(end);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return 0;
  const dayMs = 86_400_000;
  let count = 0;
  for (let t = startMs + dayMs; t <= endMs; t += dayMs) {
    const weekday = new Date(t).getUTCDay();
    if (weekday !== 0 && weekday !== 6) count += 1;
  }
  return count;
}

/** Python `staleness_gate`. */
export function stalenessGate(
  manifestAsOf: string,
  resolvedAsOf: string,
  boundTradingDays: number = STALE_BOUND_TRADING_DAYS,
): { ok: boolean; stale_days: number } {
  const staleDays = tradingDaysBetween(manifestAsOf, resolvedAsOf);
  return { ok: staleDays <= boundTradingDays, stale_days: staleDays };
}

function isManifest(value: unknown): value is Manifest {
  if (!value || typeof value !== "object") return false;
  const candidate = value as { version?: unknown; as_of?: unknown };
  return typeof candidate.version === "number" && typeof candidate.as_of === "string";
}

/** Read and validate the manifest. Version 1 only — the writer's contract. */
export async function readManifest(deps: ReadDeps): Promise<Manifest> {
  const object = await deps.bucket.get(MANIFEST_KEY);
  if (!object) {
    throw new ReadPathError("manifest_missing", `R2Error: manifest missing at ${MANIFEST_KEY}`);
  }
  const raw: unknown = await object.json();
  if (!isManifest(raw)) {
    throw new ReadPathError("manifest_invalid", "R2Error: manifest is not readable");
  }
  if (raw.version !== 1) {
    throw new ReadPathError("unsupported_manifest", `unsupported manifest version ${raw.version}`);
  }
  return raw;
}

/**
 * Manifest reads are memoised under the same 900s window as the payloads: the
 * manifest is one small object, but a read-path request that hits the cache
 * should not spend an R2 GET on it either.
 */
const MANIFEST_CACHE_KEY = "manifest";

async function readManifestCached(deps: ReadDeps): Promise<Manifest> {
  const hit = cacheGet(deps, MANIFEST_CACHE_KEY);
  if (hit !== null) return JSON.parse(hit) as Manifest;
  const manifest = await readManifest(deps);
  const cache = deps.cache;
  if (cache)
    cache.set(MANIFEST_CACHE_KEY, {
      at: deps.now?.() ?? Date.now(),
      payload: JSON.stringify(manifest),
    });
  return manifest;
}

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Fetch one sealed generation and verify it against the manifest digest, the
 * same integrity check `R2HistoryStore.get_generation` performs in Python.
 */
async function readVerifiedGeneration(
  deps: ReadDeps,
  objectKey: string,
  sha256: string,
): Promise<ArrayBuffer> {
  const object = await deps.bucket.get(objectKey);
  if (!object) {
    throw new ReadPathError("missing_object", `R2Error: generation missing at ${objectKey}`);
  }
  const bytes = await object.arrayBuffer();
  if ((await sha256Hex(bytes)) !== sha256.toLowerCase()) {
    throw new ReadPathError("sha_mismatch", `R2Error: sha256 mismatch for ${objectKey}`);
  }
  return bytes;
}

/** Resolve `as_of`: explicit argument, else the manifest seal. */
function resolveAsOf(manifest: Manifest, requested: string | undefined): string {
  const seal = String(manifest.as_of).slice(0, 10);
  const resolved = (requested ?? seal).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(resolved)) {
    throw new ReadPathError("bad_as_of", "as_of must be an ISO date (YYYY-MM-DD)");
  }
  if (resolved > seal) {
    // Python repairs this gap with a live vendor fetch. This surface does not
    // fetch, so refuse rather than serve a history-only window as if fresh.
    throw new ReadPathError(
      "beyond_seal",
      `as_of ${resolved} is after the sealed generation ${seal}; this Worker read path serves sealed R2 data only (no live fetch)`,
    );
  }
  return resolved;
}

/** Dataset ids that are macro series (`fred__DGS10`), from the manifest objects. */
export function macroSeriesIds(manifest: Manifest): string[] {
  const ids: string[] = [];
  for (const [id, entry] of Object.entries(manifest.datasets ?? {})) {
    if (typeof entry?.object === "string" && entry.object.startsWith(MACRO_OBJECT_PREFIX)) {
      ids.push(id);
    }
  }
  return ids.sort();
}

export interface ListMarketDataEnvelope {
  as_of: string;
  version: number;
  tickers: string[];
  macro_series: string[];
  /** Seal age against today — the answer to "is this cache current?" */
  stale_today: boolean;
}

/** Manifest coverage — cheap discovery call before the window tools. */
export async function listMarketData(deps: ReadDeps): Promise<string> {
  try {
    return await listMarketDataUnsafe(deps);
  } catch (error) {
    return envelopeError(error);
  }
}

async function listMarketDataUnsafe(deps: ReadDeps): Promise<string> {
  const manifest = await readManifestCached(deps);
  const seal = String(manifest.as_of).slice(0, 10);
  const today = new Date(deps.now?.() ?? Date.now()).toISOString().slice(0, 10);
  const payload: ListMarketDataEnvelope = {
    as_of: seal,
    version: manifest.version ?? 1,
    tickers: manifestTickers(manifest).sort(),
    macro_series: macroSeriesIds(manifest),
    stale_today: !stalenessGate(seal, today).ok,
  };
  return JSON.stringify(payload);
}

export interface PriceHistoryQuery {
  ticker: string;
  lookback?: number;
  asOf?: string;
}

/**
 * Sealed OHLCV window for one ticker (newest `lookback` bars at `as_of`).
 *
 * Envelope: `{as_of, sealed_as_of, rows, stale, live_overlap}`. `rows` are the
 * same shape `/v1/market/closes` returns (`shapeCloses`), so the HTTP and MCP
 * surfaces cannot drift. `live_overlap: "not_fetched"` states the difference
 * from the Python technicals envelope instead of hiding it.
 */
export async function readPriceHistory(deps: ReadDeps, query: PriceHistoryQuery): Promise<string> {
  try {
    return await readPriceHistoryUnsafe(deps, query);
  } catch (error) {
    return envelopeError(error);
  }
}

async function readPriceHistoryUnsafe(deps: ReadDeps, query: PriceHistoryQuery): Promise<string> {
  const rejected = lookbackError(query.lookback ?? 20);
  if (rejected !== null) return errorPayload(rejected);
  const lookback = boundedLookback(query.lookback ?? 20);
  const manifest = await readManifestCached(deps);
  const seal = String(manifest.as_of).slice(0, 10);
  const resolved = resolveAsOf(manifest, query.asOf);
  const cacheKey = `price:${normalizeTicker(query.ticker)}:${resolved}:${lookback}`;
  const cached = cacheGet(deps, cacheKey);
  if (cached !== null) return cached;

  const pointer = resolvePointer(manifest, query.ticker);
  if (!pointer) throw unknownTicker(query.ticker);
  const bytes = await readVerifiedGeneration(deps, pointer.object, pointer.sha256);
  const decoded = await (deps.decode ?? defaultDecode)(bytes);
  const rows = shapeCloses(decoded).filter((row) => row.date <= resolved);
  const stale = !stalenessGate(seal, resolved).ok;
  const payload = JSON.stringify({
    as_of: resolved,
    sealed_as_of: seal,
    rows: rows.slice(-lookback),
    stale,
    live_overlap: "not_fetched",
  });
  cachePut(deps, cacheKey, payload, stale);
  return payload;
}

export interface MacroQuery {
  seriesIds: string[];
  lookback?: number;
  asOf?: string;
}

/**
 * Sealed macro window per series id.
 *
 * Envelope shape matches the Python `digiquant_get_macro_series` R2 path:
 * `{as_of, series: {<id>: {latest, window}}, stale}`.
 */
export async function readMacroSeries(deps: ReadDeps, query: MacroQuery): Promise<string> {
  try {
    return await readMacroSeriesUnsafe(deps, query);
  } catch (error) {
    return envelopeError(error);
  }
}

async function readMacroSeriesUnsafe(deps: ReadDeps, query: MacroQuery): Promise<string> {
  const rejected = lookbackError(query.lookback ?? 6);
  if (rejected !== null) return errorPayload(rejected);
  if (!Array.isArray(query.seriesIds) || query.seriesIds.length === 0) {
    return errorPayload("series_ids must be a non-empty array");
  }
  const lookback = boundedLookback(query.lookback ?? 6);
  const manifest = await readManifestCached(deps);
  const seal = String(manifest.as_of).slice(0, 10);
  const resolved = resolveAsOf(manifest, query.asOf);
  const cacheKey = `macro:${[...query.seriesIds].sort().join(",")}:${resolved}:${lookback}`;
  const cached = cacheGet(deps, cacheKey);
  if (cached !== null) return cached;

  const datasets = manifest.datasets ?? {};
  const series: Record<
    string,
    { latest: Record<string, unknown>; window: Array<Record<string, unknown>> }
  > = {};
  for (const seriesId of query.seriesIds) {
    const pointerObject = await deps.bucket.get(macroPointerKey("fred", seriesId));
    if (!pointerObject) throw unknownSeries(seriesId);
    const generationKey = (await pointerObject.text()).trim();
    // Python resolves the digest by scanning the manifest for the pointer's
    // generation object; an unlisted generation is an unknown series, not an
    // unverified read.
    const entry = Object.values(datasets).find(
      (candidate) => typeof candidate?.object === "string" && candidate.object === generationKey,
    );
    if (!entry?.sha256) throw unknownSeries(seriesId);
    const bytes = await readVerifiedGeneration(deps, generationKey, String(entry.sha256));
    const decoded = await (deps.decode ?? defaultDecode)(bytes);
    const rows = decoded
      .map((row) => ({ ...row, _date: isoDate(row.obs_date ?? row.date) }))
      .filter((row) => row._date <= resolved)
      .sort((a, b) => a._date.localeCompare(b._date))
      .map(({ _date, ...rest }) => rest);
    const latest = rows.length > 0 ? rows[rows.length - 1] : {};
    series[seriesId] = { latest, window: rows.slice(-lookback) };
  }
  const stale = !stalenessGate(seal, resolved).ok;
  const payload = JSON.stringify({ as_of: resolved, series, stale });
  cachePut(deps, cacheKey, payload, stale);
  return payload;
}

function cacheGet(deps: ReadDeps, key: string): string | null {
  const cache = deps.cache;
  if (!cache) return null;
  const hit = cache.get(key);
  if (!hit) return null;
  const now = deps.now?.() ?? Date.now();
  if (now - hit.at >= TTL_MS) {
    cache.delete(key);
    return null;
  }
  return hit.payload;
}

/** Python rule (#3780 Task 7 M1): never cache a stale-flagged payload. */
function cachePut(deps: ReadDeps, key: string, payload: string, stale: boolean): void {
  if (!deps.cache || stale) return;
  deps.cache.set(key, { at: deps.now?.() ?? Date.now(), payload });
}

/** The tool surface. Names match the Python server where the semantics match. */
export function createDigiQuantMcpServer(deps: ReadDeps): McpServer {
  const server = new McpServer({ name: "digiquant", version: "2.0.0" });

  // `isError` is derived from the envelope body, never passed separately, so a
  // `{"error": ...}` payload can never be reported as a success.
  const asText = (text: string) => ({
    content: [{ type: "text" as const, text }],
    ...(isErrorEnvelope(text) ? { isError: true } : {}),
  });

  server.registerTool(
    "digiquant_list_market_data",
    {
      title: "List sealed market data",
      description:
        "Manifest coverage of the sealed R2 market-data cache: seal date, price tickers and macro series ids. Call this first to learn what the window tools can serve.",
    },
    async () => {
      try {
        return asText(await listMarketData(deps));
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  server.registerTool(
    "digiquant_get_price_history",
    {
      title: "Sealed price history",
      description:
        "Sealed OHLCV bars for one ticker from the R2 market-data cache (the same generation /v1/market/closes serves). Sealed data only: an as_of after the manifest seal is an error, because this Worker read path does not fetch live vendor data and does not compute indicators.",
      inputSchema: {
        ticker: z.string().describe("Ticker symbol, e.g. SPY or BRK/B."),
        lookback: z
          .number()
          .int()
          .optional()
          .describe("Number of newest bars to return (1..500). Default 20."),
        as_of: z
          .string()
          .optional()
          .describe("ISO date (YYYY-MM-DD) at or before the manifest seal. Default: the seal."),
      },
    },
    async ({ ticker, lookback, as_of }) => {
      try {
        return asText(await readPriceHistory(deps, { ticker, lookback, asOf: as_of }));
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  server.registerTool(
    "digiquant_get_macro_series",
    {
      title: "Sealed macro series",
      description:
        "Sealed macro observations per FRED series id from the R2 cache. Envelope: {as_of, series: {<id>: {latest, window}}, stale}. Unknown series are an error, never an empty window.",
      inputSchema: {
        series_ids: z.array(z.string()).describe('FRED series ids, e.g. ["DGS10", "VIXCLS"].'),
        lookback: z
          .number()
          .int()
          .optional()
          .describe("Observations per series (1..500). Default 6."),
        as_of: z
          .string()
          .optional()
          .describe("ISO date (YYYY-MM-DD) at or before the manifest seal. Default: the seal."),
      },
    },
    async ({ series_ids, lookback, as_of }) => {
      try {
        return asText(
          await readMacroSeries(deps, { seriesIds: series_ids, lookback, asOf: as_of }),
        );
      } catch (error) {
        return errorResult(error);
      }
    },
  );

  return server;
}

function isErrorEnvelope(text: string): boolean {
  try {
    const parsed: unknown = JSON.parse(text);
    return (
      typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) && "error" in parsed
    );
  } catch {
    return false;
  }
}

function errorResult(error: unknown): {
  content: Array<{ type: "text"; text: string }>;
  isError: boolean;
} {
  const text =
    error instanceof ReadPathError
      ? errorPayload(error.envelope)
      : errorPayload(
          `${(error as Error)?.name ?? "Error"}: ${(error as Error)?.message ?? String(error)}`,
        );
  return { content: [{ type: "text", text }], isError: true };
}

export interface McpRouteOptions {
  bucket: R2BucketLike;
  /** Edge key (`MCP_EDGE_KEY`). Empty disables only the static-key path. */
  edgeKey?: string;
  /** digikey JWKS/issuer/audience, for the `Authorization: Bearer` path. */
  authEnv?: McpEdgeAuthEnv;
  cache?: CacheStore;
  now?: () => number;
  decode?: ParquetDecode;
}

/** JSON-RPC error body for transport-level failures (never an HTML error page). */
function rpcErrorBody(message: string): Record<string, unknown> {
  return { jsonrpc: "2.0", error: { code: -32000, message }, id: null };
}

/**
 * Route handler for `mcp.digithings.ai` (and any host routed here):
 * `GET /healthz` liveness, `POST /mcp` MCP, everything else 404/405.
 *
 * Auth is the `/_stack/mcp/*` gate (`./mcp-edge-auth`): either a digikey JWT
 * carrying `digiquant:backtest` (the scope digikey already mints for this
 * service), or the static `x-digi-mcp-key` equal to `MCP_EDGE_KEY`
 * (compose/self-host, where no digikey mints a token). No credential source
 * configured at all is a 503; a bad/absent credential is 401; a valid JWT
 * without the scope is 403.
 */
export async function handleDigiQuantMcp(
  request: Request,
  options: McpRouteOptions,
): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === "/healthz") {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return Response.json(rpcErrorBody("healthz is GET only"), { status: 405 });
    }
    return Response.json({ status: "ok", service: "digiquant-mcp", backend: "r2" });
  }

  if (url.pathname !== DIGIQUANT_MCP_PATH) {
    return new Response(`digiquant-mcp: unknown path ${url.pathname}`, { status: 404 });
  }

  const expectedKey = (options.edgeKey ?? "").trim();
  const authEnv = options.authEnv ?? {};
  // Neither credential source exists: refuse with the operator signal rather
  // than answering 401 to a caller who could never have had a credential.
  if (!expectedKey && !authEnv.DIGIKEY_JWKS_URL?.trim()) {
    return new Response("digiquant-mcp: MCP_EDGE_KEY is not configured", { status: 503 });
  }
  const decision = await authorizeMcpEdge({
    request,
    serverId: "digiquant",
    expectedKey,
    env: authEnv,
  });
  if (!decision.ok) {
    const body =
      decision.status === 403 ? "digiquant-mcp: forbidden" : "digiquant-mcp: unauthorized";
    return new Response(body, {
      status: decision.status,
      headers: { "www-authenticate": 'Bearer realm="digikey"' },
    });
  }

  if (request.method !== "POST") {
    // Stateless server: no server-initiated SSE stream (GET) and no session to
    // delete (DELETE). MCP clients treat 405 as "JSON responses only".
    return Response.json(rpcErrorBody("method not allowed"), { status: 405 });
  }

  const server = createDigiQuantMcpServer(options);
  const transport = new WebStandardStreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  try {
    await server.connect(transport);
    const response = await transport.handleRequest(request);
    void transport.close().catch(() => undefined);
    return response;
  } catch (error) {
    return Response.json(rpcErrorBody(`${(error as Error)?.name ?? "Error"}: ${String(error)}`), {
      status: 500,
    });
  }
}
