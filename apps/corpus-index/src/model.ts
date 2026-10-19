/** Workers AI multilingual embedder. 1024-dim. Do not mix with 384-dim MiniLM vectors. */
export const EMBED_MODEL_ID = "@cf/baai/bge-m3";
export const EMBED_DIMENSIONS = 1024;

/** Closed tickets stay indexed until a later retention decision. */
export const RETAIN_CLOSED = "all" as const;

export const CURSOR_OVERLAP_MS = 10 * 60 * 1000;

export function overlapCursor(iso: string, now = Date.now()): string {
  const parsed = Date.parse(iso);
  const base = Number.isFinite(parsed) ? parsed : now;
  return new Date(base - CURSOR_OVERLAP_MS).toISOString();
}

export function isWeeklyReconcile(now: Date): boolean {
  return now.getUTCDay() === 0;
}
