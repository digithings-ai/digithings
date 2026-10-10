import type { BlockKind } from "../../../../clients/digiquant-tui/src/catalog";
import { presentResponse, type ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { officialApiBase } from "@/lib/official-api";

export type OfficialRead = { result: ReadResult; data: unknown };

async function readBody(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function dataOf(body: unknown, result: ReadResult): unknown {
  if (result.status === "error" || result.status === "stub") return null;
  if (!body || typeof body !== "object" || !("data" in body)) return null;
  return (body as { data: unknown }).data;
}

/** One official dashboard-api read, plus the data payload when it is safe to paint. */
export async function readOfficial(route: string, kind: BlockKind, signal?: AbortSignal): Promise<OfficialRead> {
  let res: Response;
  try {
    res = await fetch(`${officialApiBase()}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { result: { status: "error", lines: [], asOf: null }, data: null };
    return { result: { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null }, data: null };
  }
  const body = await readBody(res);
  const result = presentResponse(route, res.status, body, kind);
  return { result, data: dataOf(body, result) };
}

/** One official dashboard-api read, painted by the terminal's formatter. */
export async function readDeskBlock(route: string, kind: BlockKind, signal?: AbortSignal): Promise<ReadResult> {
  const { result } = await readOfficial(route, kind, signal);
  return result;
}

/** One official write. A non-2xx stays an error line. Stub envelopes are withheld. */
export async function postOfficial(route: string, payload: unknown, signal?: AbortSignal): Promise<OfficialRead> {
  let res: Response;
  try {
    res = await fetch(`${officialApiBase()}${route}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  } catch {
    if (signal?.aborted) return { result: { status: "error", lines: [], asOf: null }, data: null };
    return { result: { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null }, data: null };
  }
  const body = await readBody(res);
  const result = presentResponse(route, res.status, body, "fields");
  return { result, data: dataOf(body, result) };
}
