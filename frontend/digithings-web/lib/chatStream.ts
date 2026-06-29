/** NDJSON wire format for POST /api/chat. */

export type VaultHitSummary = { title: string; path: string };

export type ChatActivity =
  | { kind: "status"; message: string }
  | { kind: "tool_call"; name: string; query: string }
  | {
      kind: "tool_result";
      name: string;
      query: string;
      hits: VaultHitSummary[];
      count: number;
    }
  | { kind: "reasoning"; text: string };

export type ChatStreamEvent =
  | { type: "status"; message: string }
  | { type: "tool_call"; name: string; query: string }
  | {
      type: "tool_result";
      name: string;
      query: string;
      hits: VaultHitSummary[];
      count: number;
    }
  | { type: "reasoning"; delta: string }
  | { type: "content"; delta: string }
  | { type: "error"; message: string }
  | { type: "done" };

export const CHAT_STREAM_MIME = "application/x-ndjson";
