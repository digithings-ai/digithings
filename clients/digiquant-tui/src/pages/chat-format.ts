/** The desk says this once when every chat read is the unconfigured 502. */
export const CHAT_CLOSED = "digichat is not configured.";

/** One sentence for failed chat reads. The unconfigured 502 collapses to CHAT_CLOSED. */
export function chatFailureSentence(lines: readonly string[]): string | null {
  if (lines.some((line) => line.includes("digichat is not configured"))) return CHAT_CLOSED;
  const first = lines.map((line) => line.trim()).find((line) => line.length > 0);
  if (!first) return null;
  const stripped = first.replace(/^\/\S+ failed \(\d+\):\s*/, "").replace(/^\/\S+:\s*/, "").trim();
  if (!stripped) return null;
  return /[.!?]$/.test(stripped) ? stripped : `${stripped}.`;
}
