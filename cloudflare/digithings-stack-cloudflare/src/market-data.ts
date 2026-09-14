// src/market-data.ts — read-only R2 market data for the dashboard/digiquant-web (#4013)
import { parquetReadObjects } from "hyparquet";

const MANIFEST_KEY = "market-data/manifest.json";
const DEFAULT_ORIGINS = "https://digiquant.io,https://digithings.ai,http://localhost:3005";

export type Manifest = { version?: number; as_of?: string; datasets?: Record<string, any> };

export function manifestTickers(manifest: Manifest): string[] {
  return Object.entries(manifest.datasets ?? {})
    .filter(([, entry]) => typeof entry?.object === "string" && entry.object.startsWith("market-data/price/"))
    .map(([ticker]) => ticker);
}

export function resolvePointer(manifest: Manifest, ticker: string): { object: string; sha256: string } | undefined {
  const norm = ticker.trim().toUpperCase().replace("/", "-");
  const entry = (manifest.datasets ?? {})[norm] ?? (manifest.datasets ?? {})[ticker];
  if (!entry?.object || !entry?.sha256) return undefined;
  return { object: String(entry.object), sha256: String(entry.sha256) };
}

export function shapeCloses(rows: Array<Record<string, unknown>>) {
  return rows
    .map((r) => ({ date: String(r.date).slice(0, 10), ticker: String(r.ticker), close: Number(r.close) }))
    .filter((r) => Number.isFinite(r.close))
    .sort((a, b) => (a.date === b.date ? a.ticker.localeCompare(b.ticker) : a.date.localeCompare(b.date)));
}

export function corsHeaders(origin: string | null, allowlist: string[]): Record<string, string> {
  const headers: Record<string, string> = { Vary: "Origin" };
  if (origin && allowlist.map((o) => o.trim()).includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Methods"] = "GET, OPTIONS";
    headers["Access-Control-Max-Age"] = "86400";
  }
  return headers;
}

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function handleMarketData(
  request: Request,
  env: { MARKET_DATA: R2Bucket; MARKET_DATA_ALLOWED_ORIGINS?: string },
  url: URL,
): Promise<Response> {
  const allowlist = (env.MARKET_DATA_ALLOWED_ORIGINS ?? DEFAULT_ORIGINS).split(",");
  const cors = corsHeaders(request.headers.get("Origin"), allowlist);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

  const manifestObj = await env.MARKET_DATA.get(MANIFEST_KEY);
  if (!manifestObj) return Response.json({ error: "manifest missing" }, { status: 503, headers: cors });
  const manifest = (await manifestObj.json()) as Manifest;

  if (url.pathname === "/v1/market/tickers") {
    return Response.json(
      { as_of: manifest.as_of ?? null, tickers: manifestTickers(manifest).sort() },
      { headers: { ...cors, "Cache-Control": "public, max-age=300" } },
    );
  }

  const tickers = (url.searchParams.get("tickers") ?? "").split(",").map((t) => t.trim()).filter(Boolean);
  const from = url.searchParams.get("from") ?? "1970-01-01";
  const to = url.searchParams.get("to") ?? manifest.as_of ?? "9999-12-31";
  if (!tickers.length) return Response.json({ error: "tickers required" }, { status: 400, headers: cors });

  const rows: Array<Record<string, unknown>> = [];
  for (const ticker of tickers.slice(0, 25)) {
    const pointer = resolvePointer(manifest, ticker);
    if (!pointer) continue;
    const object = await env.MARKET_DATA.get(pointer.object);
    if (!object) continue;
    const bytes = await object.arrayBuffer();
    if ((await sha256Hex(bytes)) !== pointer.sha256) {
      return Response.json({ error: `sha mismatch for ${ticker}` }, { status: 502, headers: cors });
    }
    const parsed = await parquetReadObjects({ file: bytes, columns: ["date", "ticker", "close"] });
    rows.push(...(parsed as Array<Record<string, unknown>>).filter((r) => {
      const d = String(r.date).slice(0, 10);
      return d >= from && d <= to;
    }));
  }
  return Response.json(
    { as_of: manifest.as_of ?? null, rows: shapeCloses(rows) },
    { headers: { ...cors, "Cache-Control": "public, max-age=300" } },
  );
}
