"use client";

import { useState } from "react";
import { Button } from "@digithings/ui/ui";
import { Thread, type ThreadComponents } from "@digithings/ui/chat/thread";
import { writeHandoff, type ChatMessage } from "@/lib/chatHandoff";
import { DigichatFixtureRuntime } from "./digichat-fixture-runtime";
import { DigichatThreadWelcome } from "./digichat-thread-welcome";
import { ASK_PLACEHOLDER, ASK_SUGGESTIONS, ASK_WELCOME, welcomeBody } from "./digichat-welcome-config";
import { GROUPED_LABEL } from "./label";

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
 * interception is gone and the canned turn streams in place. What replaces it is
 * the way out: as soon as an answer exists, an expand control appears in the
 * frame's top-right corner and takes the whole conversation to the real chat.
 *
 * That last part is why the transcript is held here. The in-page Thread owns the
 * conversation in its own state, and `ChatEmbedShell` seeds the real embed from a
 * handoff of `{role, content}` pairs — so passing the transcript through on
 * expand is what makes `/chat` open with the conversation already in it, rather
 * than a fresh thread. A cube that iframed `/embed` directly could never do this:
 * its transcript would be cross-origin and unreachable.
 *
 * It is still a simulation, and it says so: the canned answers are badged
 * `example`, and the note under the box states that nothing typed here reaches
 * the container. Expanding is the moment that stops being true.
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
 * The height is the round-4 change: `17rem` is the measured height of the empty
 * cluster (welcome, example rows, composer), and the frame grows to a reading
 * height the moment there is an answer — "try to make it as tall as possible so
 * you could actually read the answer". `position: relative` is for the expand
 * control in the corner; `--surface` keeps the whole widget on one panel tone.
 */
const STAGE_STYLE = {
  height: "17rem",
  marginTop: 0,
  background: "var(--surface)",
  position: "relative",
  transition: "height .45s var(--ease)",
} as const;

const STAGE_OPEN_STYLE = { ...STAGE_STYLE, height: "clamp(24rem, 48vh, 32rem)" } as const;

export function QuickAsk({ className }: { className?: string }) {
  const [transcript, setTranscript] = useState<ChatMessage[]>([]);
  const answered = transcript.some((message) => message.role === "assistant");

  /** Take the whole conversation to the real chat, which seeds from it. */
  function expand() {
    writeHandoff(transcript, "");
    window.location.href = "/chat";
  }

  return (
    <div className={className}>
      <div className="flex flex-col gap-[0.7rem]">
        <div className="flex flex-wrap items-baseline justify-between gap-x-[1rem] gap-y-[0.4rem]">
          <p className={`m-0 ${GROUPED_LABEL}`}>digichat</p>
          <p className="m-0 font-mono text-[0.68rem] text-ink-mute">
            example answers · the full chat opens in the container
          </p>
        </div>
        <div
          className="aui-theme-stage [&_.aui-thread-root]:bg-surface! [&_.aui-thread-viewport-footer]:bg-surface!"
          style={answered ? STAGE_OPEN_STYLE : STAGE_STYLE}
        >
          {/* The way out, and it only appears once there is something to take.
              An expand affordance rather than a "continue" button because the
              conversation is the thing being opened, not a question being
              forwarded — the visitor already has the answer, and /chat should
              open with it, not ahead of it. */}
          {answered ? (
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={expand}
              aria-label="Open this conversation in digichat"
              className="absolute end-[0.6rem] top-[0.6rem] z-10 bg-surface font-mono text-[0.68rem] uppercase tracking-[0.06em] text-ink-soft"
            >
              <span aria-hidden="true" className="text-[0.8rem] leading-none">
                ⤢
              </span>
              expand
            </Button>
          ) : null}
          <DigichatFixtureRuntime suggestions={ASK_SUGGESTIONS} onTranscript={setTranscript}>
            <Thread
              autoFocus={false}
              components={THREAD_COMPONENTS}
              placeholder={ASK_PLACEHOLDER}
              composerLayout="compact"
            />
          </DigichatFixtureRuntime>
        </div>
        <p className="m-0 font-mono text-[0.68rem] leading-[1.6] text-ink-mute">
          These answers are canned, and nothing typed here reaches the container. Expand once an
          answer lands and the same conversation continues in the real chat.
        </p>
      </div>
    </div>
  );
}
