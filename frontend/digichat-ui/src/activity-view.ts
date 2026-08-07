/**
 * Activity → canon projection (#1418 gap 6).
 *
 * `DigiChatActivity` is the wire vocabulary every backend provider emits (see
 * digichat's `lib/chat-activity.ts`); the shared chat family in
 * `@digithings/web` is the *rendering* vocabulary — collapsible `ChatToolCall`
 * rows, a `ChatThinking` disclosure, `ChatWidgetFrame` cards. The two do not
 * line up field-for-field, so this module is the boundary adapter between
 * them: one pure function, no JSX, no DOM. `ChatActivities` renders whatever
 * it returns and holds no mapping logic of its own.
 *
 * Keeping the projection separate from the component is what makes the mapping
 * testable in a plain node environment (no jsdom in either consumer's vitest
 * setup) — and it is the seam to extend when the protocol grows a field, so
 * neither the shared primitives nor the renderer has to fork.
 *
 * Fidelity notes — where the wire model carries less than the canon can show:
 *
 *  - **No timings.** `ActivitySpan` has no duration field, so nothing can fill
 *    `ChatToolCall`'s `duration` slot with real milliseconds. It is the head
 *    row's right-aligned mono meta slot, so we spend it on the outcome count
 *    (`3 notes` / `no hits`) — the fact a reader actually wants folded, and
 *    the only way a collapsed result row stays honest about whether the search
 *    found anything.
 *  - **`status` rows have already lost their structure.** By the time a
 *    withheld-documents or failed-search outcome reaches here it is prose
 *    (`Found results for "x".`), with the tool name and query dissolved into
 *    the string upstream. Parsing them back out of prose would be guesswork,
 *    so these render as canon system asides rather than as fake tool rows.
 *  - **Reasoning arrives as one blob**, not pre-segmented steps, so it maps to
 *    `ChatThinking`'s `children` disclosure rather than its railed `steps`
 *    list. See `ChatThinking`'s own docstring, which prescribes exactly this.
 */
import type { ChatToolCallStatus } from "@digithings/web";
import type { DigiChatActivity, VaultHitSummary } from "./types";

/**
 * One rendered row of the agent chain. Each variant names the shared primitive
 * it becomes, and carries only what that primitive's props need.
 */
export type CanonActivityRow =
  | {
      /** → <ChatToolCall> */
      kind: "tool";
      key: string;
      /** Head name, rendered in the accent. */
      name: string;
      /** Head `(args)` — the query, when the provider sent one. */
      args?: string;
      status: ChatToolCallStatus;
      /** Right-aligned head meta — an outcome count, not a timing (see above). */
      meta?: string;
      /** Retrieved documents, rendered as the fold-out body. */
      sources?: VaultHitSummary[];
      /**
       * Start expanded. `ChatToolCall` renders its body ONLY while open, so a
       * folded row's content is absent from the server markup entirely — see
       * `toCanonRows` for why citations, and only citations, opt in.
       */
      defaultOpen?: boolean;
    }
  | {
      /** → <ChatThinking> */
      kind: "thinking";
      key: string;
      label: string;
      text: string;
    }
  | {
      /** → <ChatWidgetFrame variant="card"> */
      kind: "brief";
      key: string;
      themes: { label: string; summary: string }[];
      questions?: string[];
    }
  | {
      /** → <ChatMessage role="system"> — a `·` aside. */
      kind: "aside";
      key: string;
      message: string;
    };

/** `3 notes` / `1 note` / `no hits` — the folded outcome read. */
export function outcomeMeta(count: number): string {
  if (count <= 0) return "no hits";
  return `${count} note${count === 1 ? "" : "s"}`;
}

/**
 * Projects the wire activities onto canon rows, in order.
 *
 * Keyed by IDENTITY, not position. Position is not stable: `toDigiChatActivity`
 * appends the reasoning row last, after every tool row, so its index climbs each
 * time a tool arrives; it also rewrites a row in place from `tool_call` to
 * `tool_result` (kind is part of any composite key), and its final filter drops
 * orphaned placeholders, shifting everything after them. Since `ChatThinking`
 * and `ChatToolCall` are uncontrolled, a changed key is an unmount — so an
 * index key collapsed a disclosure the reader had opened, mid-stream, and
 * removed its text from the DOM.
 *
 * Reasoning is a singleton per turn, so it keys as itself. Tool rows key on
 * name+query, which is the identity the producer already groups by internally.
 * A trailing index still disambiguates genuine duplicates.
 */
/**
 * A key that survives the row moving. `reasoning` is one per turn so it needs no
 * suffix; tool rows carry name+query (the producer's own grouping key) and a
 * trailing index only to separate true duplicates.
 */
function identityKey(activity: DigiChatActivity, i: number): string {
  switch (activity.kind) {
    case "reasoning":
      return "reasoning";
    case "tool_call":
    case "tool_result":
      return `tool:${activity.name}|${"query" in activity ? (activity.query ?? "") : ""}`;
    default:
      return `${activity.kind}-${i}`;
  }
}

export function toCanonRows(activities: readonly DigiChatActivity[]): CanonActivityRow[] {
  return activities.map((activity, i): CanonActivityRow => {
    const key = identityKey(activity, i);
    switch (activity.kind) {
      case "tool_call":
        // Still in flight: no body, so the head renders as a plain row with a
        // breathing ellipsis and no caret.
        return {
          kind: "tool",
          key,
          name: activity.name,
          ...(activity.query ? { args: activity.query } : {}),
          status: "running",
        };

      case "tool_result":
        return {
          kind: "tool",
          key,
          name: activity.name,
          ...(activity.query ? { args: activity.query } : {}),
          status: "ok",
          meta: outcomeMeta(activity.count),
          // A zero-hit result gets no body at all — an expandable block that
          // folds open onto nothing is worse than a plain settled row.
          //
          // Non-empty hits attach as `sources` but stay folded (`defaultOpen`
          // unset). Claude Code / opencode tool-row grammar: head on one line,
          // reader expands for the body. A retrieved chunk can run to several
          // hundred characters, and several searches on one answer used to
          // unfold every one onto the screen at once. (Closed `ChatToolCall`
          // mounts no body, so citations are absent from SSR until expand —
          // accepted trade for the chain staying scannable.)
          ...(activity.hits.length ? { sources: activity.hits } : {}),
        };

      case "trace":
        // An opaque upstream step. It has a label but no arguments and no
        // output, so it rebuilds as a bodyless tool row — the canon's own
        // read for "a step that ran".
        return {
          kind: "tool",
          key,
          name: activity.label,
          status: activity.done ? "ok" : "running",
        };

      case "reasoning":
        return { kind: "thinking", key, label: "reasoning", text: activity.text };

      case "brief":
        return {
          kind: "brief",
          key,
          themes: activity.themes,
          ...(activity.questions?.length ? { questions: activity.questions } : {}),
        };

      case "status":
        return { kind: "aside", key, message: activity.message };

      default: {
        const _exhaustive: never = activity;
        void _exhaustive;
        return { kind: "aside", key, message: "" };
      }
    }
  });
}

/**
 * The step to show in the waiting caret: what the agent is doing *right now*,
 * or nothing.
 *
 * The caret used to cycle a hard-coded script — "thinking", "routing through
 * digigraph", "gathering context", "composing the answer" — on a ~10s loop
 * regardless of what was happening. It read as a placeholder because it was
 * one: none of those words were tied to any real step, and two of them named
 * a backend this transcript may not even be talking to.
 *
 * So the label comes from the stream or there is no label. `undefined` means
 * the caller shows a bare blinking cursor — an honest "something is happening"
 * beats a confident sentence about the wrong thing.
 *
 * Scans from the end because the newest unfinished step is the current one.
 * A tool row is "unfinished" until a tool_result for the same name arrives;
 * matching on name alone (not name+query) is deliberate, since a call's query
 * is often still empty while it is in flight — that is exactly the case this
 * has to cover.
 */
export function liveActivityLabel(activities: DigiChatActivity[]): string | undefined {
  const settledTools = new Set<string>();
  for (let i = activities.length - 1; i >= 0; i -= 1) {
    const activity = activities[i];
    switch (activity.kind) {
      case "tool_result":
        settledTools.add(activity.name);
        break;
      case "tool_call": {
        if (settledTools.has(activity.name)) break;
        const query = activity.query?.trim();
        return query ? `Searching for "${query}"` : "Searching…";
      }
      case "trace":
        if (!activity.done) return activity.label;
        break;
      default:
        break;
    }
  }
  return undefined;
}
