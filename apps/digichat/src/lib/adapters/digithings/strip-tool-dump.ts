/**
 * Strip digigraph SSE tool-call/result markup from assistant answer prose.
 * Activity Sources come from digigraph_trace — not from these streamed blocks.
 */
export function stripToolDumpFromAnswerDelta(text: string): string {
  if (!text) return text;
  let out = text;
  // Open WebUI formatter: collapsible tool call/result blocks.
  out = out.replace(/<details\b[^>]*>[\s\S]*?<\/details>\s*/gi, "");
  // Reasoning streamed as a synthetic thinking block for Open WebUI clients.
  out = out.replace(/<thinking>[\s\S]*?<\/thinking>\s*/gi, "");
  // Neutral formatter: Tool: name + fenced JSON arguments.
  out = out.replace(/^Tool:\s*\S+[^\n]*\n```json[\s\S]*?```\s*/gm, "");
  return out;
}
