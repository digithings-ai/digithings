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
 * Index-keyed: the activity list is rebuilt from scratch on every render of a
 * streaming turn (see `toDigiChatActivity`), and rows are append-mostly — so
 * position is the stable identity here, and two rows that stringify the same
 * (a repeated trace label, two identical reasoning blobs) still get distinct
 * React keys.
 */
export function toCanonRows(activities: readonly DigiChatActivity[]): CanonActivityRow[] {
  return activities.map((activity, i): CanonActivityRow => {
    const key = `${activity.kind}-${i}`;
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
          // Retrieved documents, by contrast, start EXPANDED. The canon folds
          // tool output by default because it is usually noise, but citations
          // are the opposite: "I cite real docs rather than guess" is the whole
          // claim this product makes, and the sources are what lets a reader
          // check it. Folding them would also put them behind a click —
          // `ChatToolCall` renders no body at all while closed, so they would
          // be missing from the server markup, invisible without client JS and
          // invisible to a crawler. The genuinely noisy rows (reasoning chains,
          // bare trace steps) stay folded.
          ...(activity.hits.length ? { sources: activity.hits, defaultOpen: true } : {}),
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
