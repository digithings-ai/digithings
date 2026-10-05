export type VaultHitSummary = {
  title: string;
  path: string;
  tier?: string;
  year?: number;
  snippet?: string;
  /** Full note body from digivault_get_note — never an invented URL. */
  body?: string;
};

/**
 * Why a `status` row exists, when it is about a tool. Absent means a quiet note
 * about the turn — "results exist but this detail level withholds them" — and it
 * is the only reading a status without an outcome may have.
 *
 * `query` is absent when the turn never knew one, never `""`. `state`:
 *   - `failed`     the tool was asked and did not answer
 *   - `unreadable` the tool answered and this layer cannot read the answer; an
 *                  honest unknown, and never an empty result
 */
export type DigiChatStatusOutcome = {
  name: string;
  query?: string;
  state: "failed" | "unreadable";
};

export type DigiChatActivity =
  | { kind: "status"; message: string; outcome?: DigiChatStatusOutcome }
  | { kind: "tool_call"; name: string; query: string }
  | {
      kind: "tool_result";
      name: string;
      query: string;
      hits: VaultHitSummary[];
      count: number;
    }
  | { kind: "reasoning"; text: string }
  | { kind: "trace"; label: string; done: boolean }
  | {
      kind: "brief";
      themes: { label: string; summary: string }[];
      questions?: string[];
    };

export type DigiChatMessage = {
  role: "user" | "assistant";
  content: string;
  activities?: DigiChatActivity[];
};

/**
 * Embed/controller adapter shape used by digichat's `useEmbedDigiChat` and
 * activity projection. digichat 2.0 UI is `CliThread` (assistant-ui); this is
 * not a mountable session component.
 */
export type DigiChatController = {
  messages: DigiChatMessage[];
  busy: boolean;
  error: string | null;
  quotaPrompt?: boolean;
  send: (question: string, opts?: { forceTool?: string }) => void | Promise<void>;
  stop?: () => void;
  /** Error-row retry only — not last-turn regenerate chrome. */
  onRetry?: () => void;
  /**
   * Re-answer the last user turn (drop trailing assistant, resend transcript).
   * Omit on Foundry embeds until the turn-mutation API (#3475) — truncate-and-resend
   * would append a duplicate user item on an append-only conversation.
   */
  regenerate?: () => void;
  /**
   * Replace the last user turn (and drop any following assistant), then send.
   * Empty / whitespace-only text is a no-op. Omit on Foundry for the same reason
   * as `regenerate`.
   */
  editLastUser?: (text: string) => void | Promise<void>;
  reset?: () => void;
  modelLabel?: string;
  providerIsSet?: boolean;
  openSettings?: () => void;
};
