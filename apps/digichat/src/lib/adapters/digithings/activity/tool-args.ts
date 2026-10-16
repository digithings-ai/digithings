/** Presentation-safe MCP argument extraction for activity rows. */

export function queryFromToolArgs(args: Record<string, unknown>): string | undefined {
  const query = typeof args.query === "string" && args.query.trim() ? args.query.trim() : undefined;
  if (query) return query;
  const vaultPath =
    (typeof args.vault_path === "string" && args.vault_path.trim()) ||
    (typeof args.path === "string" && args.path.trim()) ||
    "";
  if (vaultPath) return vaultPath;
  const paths = args.vault_paths;
  if (Array.isArray(paths)) {
    const n = paths.filter((p) => typeof p === "string" && p.trim()).length;
    if (n === 1) return "1 note";
    if (n > 1) return `${n} notes`;
  }
  return undefined;
}

export function argsRecord(payload: Record<string, unknown>): Record<string, unknown> | undefined {
  const raw = payload.arguments ?? payload.args;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  return undefined;
}

export function toolInputFromPayload(
  payload: Record<string, unknown>,
): Record<string, unknown> | undefined {
  const args = argsRecord(payload);
  if (args && Object.keys(args).length) return args;
  if (typeof payload.query === "string" && payload.query.trim()) {
    return { query: payload.query.trim() };
  }
  return undefined;
}
