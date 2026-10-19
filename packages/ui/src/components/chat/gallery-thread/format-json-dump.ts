/** Pretty-print tool args the same way results already use JSON.stringify(..., null, 2). */
export function formatJsonDump(value: unknown): string {
  if (value === undefined) return "";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return value;
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
      const repaired = repairPartialJson(trimmed);
      if (repaired !== undefined) {
        try {
          return JSON.stringify(JSON.parse(repaired), null, 2);
        } catch {
          /* fall through to raw text */
        }
      }
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function formatToolDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "0ms";
  const rounded = Math.round(ms);
  if (rounded < 100) return `${rounded}ms`;
  const seconds = rounded / 1000;
  if (seconds < 10) return `${(Math.round(seconds * 10) / 10).toFixed(1)}s`;
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

export function humanizeToolName(toolName: string, _argsText?: string): string {
  void _argsText;
  return toolName.trim() || "tool";
}

/**
 * Close a truncated JSON prefix (streaming tool args) so it can be parsed:
 * closes an open string, drops a dangling key / trailing comma / colon, and
 * closes open objects and arrays. Returns undefined when the text is not a
 * JSON object/array prefix.
 */
export function repairPartialJson(text: string): string | undefined {
  const src = text.trim();
  if (!src || (src[0] !== "{" && src[0] !== "[")) return undefined;
  const stack: string[] = [];
  let inString = false;
  let escaped = false;
  for (const ch of src) {
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "{" || ch === "[") stack.push(ch);
    else if (ch === "}" || ch === "]") {
      if (stack.pop() !== (ch === "}" ? "{" : "[")) return undefined;
    }
  }
  let out = src;
  if (inString) {
    if (escaped) out = out.slice(0, -1);
    out += '"';
  }
  for (let i = 0; i < 4; i++) {
    const before = out;
    out = out.replace(/\s+$/, "");
    out = out.replace(/,$/, "");
    out = out.replace(/:$/, "");
    // dangling key with no value inside an object: {"a":1,"b"
    if (stack[stack.length - 1] === "{") out = out.replace(/([{,])\s*"(?:[^"\\]|\\.)*"$/, "$1");
    out = out.replace(/,$/, "");
    // partial literal (tru, fals, nul) or number ending in '-' / '.' / 'e'
    out = out.replace(/(?<=[:\[,]\s*)(t|tr|tru|f|fa|fal|fals|n|nu|nul)$/, "");
    out = out.replace(/(?<=\d)[.eE+-]+$/, "").replace(/(?<=[:\[,]\s*)-$/, "");
    if (out === before) break;
  }
  while (stack.length) out += stack.pop() === "{" ? "}" : "]";
  return out;
}
