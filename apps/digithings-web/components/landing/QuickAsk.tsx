"use client";

import { useState } from "react";
import { Button } from "@digithings/ui/ui";
import { Thread, type ThreadComponents } from "@digithings/ui/chat/thread";
import { writeHandoff, type ChatMessage } from "@/lib/chatHandoff";
import { DigichatFixtureRuntime } from "./digichat-fixture-runtime";
import { DigichatThreadWelcome } from "./digichat-thread-welcome";
import { ASK_PLACEHOLDER, ASK_SUGGESTIONS, ASK_WELCOME, welcomeBody } from "./digichat-welcome-config";

/**
 * The FAQ band's right pane: the real digichat skin as a self-contained
 * conversation (#4429, Stage 8; reworked in round 4).
 *
 * It mounts the *product* Thread module — `@digithings/ui/chat/thread`, the same
 * subpath `/chat` and the design gallery render — inside the fixture runtime, so
 * the box draws the real welcome copy, the real example rows, the real compact
 * composer and, as a turn runs, real MCP-shaped tool rows. The welcome and the
 * examples are now read from the same record `/chat` uses (`lib/embedCopy.ts`
 * via `digichat-welcome-config.ts`), so the two surfaces open identically.
 *
 * ROUND 4: the box answers where it stands. It used to intercept every send at
 * the DOM and navigate to `/chat` before the fixture could run, which meant a
 * visitor who clicked an example watched the pane leave rather than reply. The
 * owner asked for the opposite — "make sure we're actually responding in this
 * cube… they'd get an answer streamed in this embedded view" — so the
 * interception is gone and the canned turn streams in place.
 *
 * ROUND 5: the way out is a plain button in the header row, next to the
 * `digichat` label, and the frame has ONE height. Round 4 grew the frame from
 * 17rem to a reading height the moment an answer landed and floated an overlay
 * control in the top-right corner; the owner rejected both — "you made this box
 * expand… it should be a fixed height", and the overlay was a full-height
 * column because the gallery sheet's `.aui-theme-stage > * { height: 100% }`
 * applies to every direct child, positioned or not. So the control moved out of
 * the stage (and out of that selector's reach) and into the header, the copy
 * that used to explain the container was replaced by the button itself, and the
 * frame is fixed — a taller, wider reading pane rather than one that changes
 * size under the reader's cursor.
 *
 * The transcript is held here because it is what the button carries. The
 * in-page Thread owns the conversation in its own state, and `ChatEmbedShell`
 * seeds the real embed from a handoff of `{role, content}` pairs — so passing
 * the transcript through is what makes `/chat` open with the conversation
 * already in it, rather than a fresh thread. A cube that iframed `/embed`
 * directly could never do this: its transcript would be cross-origin and
 * unreachable.
 *
 * It is still a simulation, and the canned answers are badged `example`. Round 6
 * dropped the note under the box that spelled that out ("the answers are canned
 * and nothing typed…") — the owner called it text to remove — so the badge and
 * the working full-chat control carry it instead.
 */

/** Module scope so the message tree does not re-render on parent updates. */
const THREAD_COMPONENTS: ThreadComponents = {
  Welcome: function AskWelcome() {
    return <DigichatThreadWelcome title={ASK_WELCOME.title} body={welcomeBody(ASK_WELCOME)} />;
  },
};

/**
 * The stage frame. Inline because every value has to outrank the gallery sheet.
 *
 * Fixed at a reading height (round 5). Round 4 varied it with the transcript,
 * which meant the band reflowed under the reader mid-answer; the owner asked for
 * one height — "it should be a fixed height, it shouldn't get longer" — and for
 * the extra room to come from the band's split instead, which is why the FAQ grid
 * in `LandingPage.tsx` now gives this column more than half the frame.
 *
 * `position: relative` is kept for the corner the old overlay used; nothing
 * absolute is positioned against it any more, but the Thread's own sticky footer
 * relies on a positioned ancestor for its scrollport.
 */
const STAGE_STYLE = {
  height: "clamp(22rem, 40vh, 30rem)",
  marginTop: 0,
  background: "var(--surface)",
  position: "relative",
} as const;

export function QuickAsk({ className }: { className?: string }) {
  const [transcript, setTranscript] = useState<ChatMessage[]>([]);

  /** Take the whole conversation to the real chat, which seeds from it. */
  function expand() {
    writeHandoff(transcript, "");
    window.location.href = "/chat";
  }

  return (
    <div className={className}>
      <div className="flex flex-col gap-[0.7rem]">
        {/* The way out, icon-only, at the pane's top-right. The owner: "the full
            screen chat button should be... in the top left or the top right just
            just the logo of full screen", and "i'd remove the digi chat title in
            the left just so we give more room to the chat pane". So the header
            row is now only the control — the `digichat` label is gone and the
            stage below spans the full column. The icon carries the meaning; the
            label lives in `aria-label` and `title` for anyone who needs words. */}
        <div className="flex items-center justify-end">
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={expand}
            aria-label="Open this conversation in the full chat"
            title="Full screen chat"
            className="px-[0.5rem] text-ink-soft"
          >
            <span aria-hidden="true" className="text-[0.9rem] leading-none">
              ⤢
            </span>
          </Button>
        </div>
        <div
          className="aui-theme-stage [&_.aui-thread-root]:bg-surface! [&_.aui-thread-viewport-footer]:bg-surface!"
          style={STAGE_STYLE}
        >
          <DigichatFixtureRuntime suggestions={ASK_SUGGESTIONS} onTranscript={setTranscript}>
            <Thread
              autoFocus={false}
              components={THREAD_COMPONENTS}
              placeholder={ASK_PLACEHOLDER}
              composerLayout="compact"
            />
          </DigichatFixtureRuntime>
        </div>
      </div>
    </div>
  );
}
