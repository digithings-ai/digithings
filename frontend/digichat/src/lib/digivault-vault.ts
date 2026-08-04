/**
 * Digivault Supabase RPC helper — search_architecture_notes + presentation-safe
 * activity documents. Vault body text is for the model tool message only.
 */
import type { ActivityDocument } from "./chat-activity";

export const MAX_NOTE_CHARS = 1200;
export const TOP_K = 4;

export type VaultHit = {
  vault_path: string;
  title: string;
  body_markdown: string;
};

export type SearchArchitectureNotesOpts = {
  supabaseUrl: string;
  supabaseAnonKey: string;
  query: string;
  matchCount?: number;
  fetchImpl?: typeof fetch;
};

export async function searchArchitectureNotes(
  opts: SearchArchitectureNotesOpts,
): Promise<VaultHit[]> {
  const base = opts.supabaseUrl.replace(/\/+$/, "");
  const key = opts.supabaseAnonKey;
  const k = opts.matchCount ?? TOP_K;
  const fetchFn = opts.fetchImpl ?? fetch;
  const resp = await fetchFn(`${base}/rest/v1/rpc/search_architecture_notes`, {
    method: "POST",
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "content-type": "application/json",
    },
    // Parity with CF functions/api/chat.ts searchVault body field names.
    body: JSON.stringify({ query: opts.query, match_limit: k }),
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new Error(`vault search ${resp.status}: ${detail.slice(0, 200)}`);
  }
  const raw = (await resp.json()) as unknown;
  if (!Array.isArray(raw)) return [];
  const hits: VaultHit[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const r = entry as Record<string, unknown>;
    const vault_path = typeof r.vault_path === "string" ? r.vault_path : "";
    const title = typeof r.title === "string" ? r.title : vault_path;
    const body_markdown = typeof r.body_markdown === "string" ? r.body_markdown : "";
    if (!vault_path) continue;
    hits.push({ vault_path, title: title || vault_path, body_markdown });
  }
  return hits;
}

export function buildToolContext(hits: VaultHit[]): {
  toolText: string;
  activityDocuments: ActivityDocument[];
} {
  const toolText = hits
    .map((h) => {
      const body =
        h.body_markdown.length > MAX_NOTE_CHARS
          ? h.body_markdown.slice(0, MAX_NOTE_CHARS) + "\n…(truncated)"
          : h.body_markdown;
      return `## ${h.title} (${h.vault_path})\n${body}`;
    })
    .join("\n\n---\n\n");

  const activityDocuments: ActivityDocument[] = hits.map((h) => ({
    title: h.title,
    path: h.vault_path,
  }));

  return { toolText, activityDocuments };
}
