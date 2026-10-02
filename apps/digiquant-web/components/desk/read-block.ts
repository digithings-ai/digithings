import type { BlockKind } from "../../../../clients/digiquant-tui/src/catalog";
import { presentResponse, type ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { officialApiBase } from "@/lib/official-api";

/** One official dashboard-api read, painted by the terminal's formatter. */
export async function readDeskBlock(route: string, kind: BlockKind, signal?: AbortSignal): Promise<ReadResult> {
  let res: Response;
  try {
    res = await fetch(`${officialApiBase()}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { status: "error", lines: [], asOf: null };
    return { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  return presentResponse(route, res.status, body, kind);
}
