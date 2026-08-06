"use client";

/**
 * ChatActivities — the agent chain of one assistant turn, rendered in the
 * digichat terminal grammar (canon §16) on the shared chat family from
 * `@digithings/web`.
 *
 * Before #1418's gap 6 closed, this was a flat bordered `.dc-activities` box of
 * bespoke `.dc-act-*` paragraphs. It DID render all three kinds — a tool chain
 * (`.dc-act-tool`), a reasoning disclosure (`<details class="dc-act-reasoning">`)
 * and sources (`.dc-act-hits`, with title/tier/year/path/snippet) — and it
 * rendered them identically on both surfaces, because both take the same session
 * component. An earlier version of this docblock said the embed "showed no
 * tool-call chain, no reasoning disclosure and no sources" while digithings.ai
 * used canon primitives; neither half was true. What changed here is the *skin*,
 * not the presence of the information: every row is now a shared primitive
 * instead of a bespoke paragraph.
 *
 *   | activity      | primitive                          |
 *   |---------------|------------------------------------|
 *   | `tool_call`   | <ChatToolCall status="running">    |
 *   | `tool_result` | <ChatToolCall status="ok"> + hits  |
 *   | `trace`       | <ChatToolCall> (bodyless step row) |
 *   | `reasoning`   | <ChatThinking> disclosure          |
 *   | `brief`       | <ChatWidgetFrame variant="card">   |
 *   | `status`      | <ChatMessage role="system">        |
 *
 * The wire-model → props mapping lives in `../activity-view` (pure, tested);
 * this file only renders. Both surfaces get it at once — digichat `/embed` and
 * digithings-web `/chat` render the same session component.
 *
 * Styling split, and why it is this way round: the primitives carry their own
 * token utilities, which each consumer's Tailwind build already generates via
 * its `@source ".../digiweb/web/src/components/chat"`. Markup authored *here*
 * gets none of that — no consumer `@source`s this package — so anything this
 * file adds around a primitive wears a `.dc-*` class backed by `session.css`,
 * where the tokens resolve in plain CSS. Utilities in this file would silently
 * fail to generate in both apps.
 */
import {
  ChatMessage,
  ChatThinking,
  ChatToolCall,
  ChatWidgetFrame,
} from "@digithings/web";
import { toCanonRows, type CanonActivityRow } from "../activity-view";
import type { DigiChatActivity, VaultHitSummary } from "../types";

/**
 * Retrieved documents, as the fold-out body of a `tool_result` row.
 *
 * Not new: the previous `.dc-act-hits` list already rendered these on both
 * surfaces. `activity-view.ts` sets `defaultOpen: true` for a non-empty hit list,
 * so citations stay in the server-rendered markup rather than hiding behind a
 * click.
 */
function SourceList({ sources }: { sources: VaultHitSummary[] }) {
  return (
    <ul className="dc-act-hits">
      {/* path is not unique — two chunks of one vault document share it. */}
      {sources.map((hit, i) => (
        <li key={`${hit.path}-${i}`}>
          <span className="dc-act-hit-title">{hit.title}</span>
          {hit.tier ? <span className="dc-act-hit-tier">{hit.tier}</span> : null}
          {typeof hit.year === "number" ? (
            <span className="dc-act-hit-year">{hit.year}</span>
          ) : null}
          <span className="dc-act-hit-path">{hit.path}</span>
          {hit.snippet ? <p className="dc-act-hit-snippet">{hit.snippet}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function ActivityRow({ row }: { row: CanonActivityRow }) {
  switch (row.kind) {
    case "tool":
      return (
        <ChatToolCall
          name={row.name}
          args={row.args}
          status={row.status}
          // Outcome count, not a timing — the protocol carries no durations.
          // See ../activity-view for why this slot is spent this way.
          duration={row.meta}
          defaultOpen={row.defaultOpen}
        >
          {row.sources ? <SourceList sources={row.sources} /> : null}
        </ChatToolCall>
      );

    case "thinking":
      return (
        <ChatThinking label={row.label} count={null}>
          <pre className="dc-act-reasoning-text">{row.text}</pre>
        </ChatThinking>
      );

    case "brief":
      return (
        <ChatWidgetFrame eyebrow="research brief" className="dc-act-brief">
          <div className="dc-act-brief-body">
            <ul className="dc-act-brief-themes">
              {row.themes.map((theme, i) => (
                <li key={`${theme.label}-${i}`}>
                  <span className="dc-act-brief-label">{theme.label}</span>
                  {theme.summary ? ` — ${theme.summary}` : ""}
                </li>
              ))}
            </ul>
            {row.questions?.length ? (
              <div className="dc-act-brief-questions">
                <p className="dc-act-brief-q-heading">Next questions</p>
                <ol>
                  {row.questions.map((question, i) => (
                    <li key={`${question}-${i}`}>{question}</li>
                  ))}
                </ol>
              </div>
            ) : null}
          </div>
        </ChatWidgetFrame>
      );

    case "aside":
      return (
        <ChatMessage role="system" tone="mute" className="dc-act-status">
          {row.message}
        </ChatMessage>
      );

    default: {
      const _exhaustive: never = row;
      void _exhaustive;
      return null;
    }
  }
}

export function ChatActivities({ activities }: { activities?: DigiChatActivity[] }) {
  if (!activities?.length) return null;
  const rows = toCanonRows(activities);
  const hasTraces = activities.some((a) => a.kind === "trace");
  return (
    <div
      className={`dc-activities${hasTraces ? " dc-activities-traces" : ""}`}
      aria-label="Agent steps"
    >
      {rows.map((row) => (
        <ActivityRow key={row.key} row={row} />
      ))}
    </div>
  );
}
