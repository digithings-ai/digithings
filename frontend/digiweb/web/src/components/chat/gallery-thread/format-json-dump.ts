/** Pretty-print tool args the same way results already use JSON.stringify(..., null, 2). */
export function formatJsonDump(value: unknown): string {
  if (value === undefined) return "";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return value;
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
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
  if (rounded < 1000) return `${rounded}ms`;
  const seconds = rounded / 1000;
  if (seconds < 10) return `${(Math.floor(seconds * 10) / 10).toFixed(1)}s`;
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

export function humanizeToolName(toolName: string, _argsText?: string): string {
  void _argsText;
  return toolName.trim() || "tool";
}
