"use client";

import { useCallback, type FormEvent, type MouseEvent } from "react";
import { Thread, type ThreadComponents } from "@digithings/ui/chat/thread";
import { writeHandoff } from "@/lib/chatHandoff";
import { DigichatFixtureRuntime } from "./digichat-fixture-runtime";
import { DigichatThreadWelcome } from "./digichat-thread-welcome";
import { ASK_PLACEHOLDER, ASK_SUGGESTIONS, ASK_WELCOME, welcomeBody } from "./digichat-welcome-config";
import { GROUPED_LABEL } from "./label";

/**
 * The FAQ band's right pane: the real digichat skin as a self-contained
 * simulation (#4429, Stage 8, point 13).
 *
 * The owner's direction: replace the hand-rolled `ChatTranscript` preview with
 * what the visitor actually gets. This mounts the *product* Thread module —
 * `@digithings/ui/chat/thread`, the same subpath `/chat` and the design gallery
 * render — inside the reference's fixture runtime, so the box draws the real
 * welcome copy, the real example rows, the real compact composer and, if a turn
 * ever runs, real MCP-shaped tool rows. It is a simulation: the runtime streams
 * canned turns and nothing here reaches the container.
 *
 * Every send leaves. A click on an example row or a submit in the composer
 * writes the one-shot handoff and goes to /chat, where `ChatEmbedShell`
 * read-and-clears it and seeds the real embed. So the visitor never waits on
 * the container's cold start from the landing page, and the fabricated sidebar
 * of a canned answer never renders here.
 *
 * Interception is DOM-level on purpose. The Thread's welcome rows are
 * `SuggestionPrimitive.Trigger send`, which sends into whatever runtime is
 * mounted; the composer's form is the one seam both Enter and the Send control
 * pass through. Catching the click at the stage and the send at the form keeps
 * the gallery Thread module untouched — no fork, no second copy of the slots.
 *
 * Deviation from the stage plan, recorded: the plan named `DigichatLauncher` as
 * the host. The launcher is a fixed-size floating panel that force-focuses its
 * close button when open, which on a landing page steals focus on load; the
 * band therefore mounts the same Thread inline in a bordered stage. Same skin,
 * same module, same config — without the corner chrome.
 */

/** Module scope so the message tree does not re-render on parent updates. */
const THREAD_COMPONENTS: ThreadComponents = {
  Welcome: function AskWelcome() {
    return <DigichatThreadWelcome title={ASK_WELCOME.title} body={welcomeBody(ASK_WELCOME)} />;
  },
};

/** The stage frame's own height. Inline because it must outrank the sheet. */
const STAGE_STYLE = { height: "clamp(19rem, 34vh, 25rem)", marginTop: 0 } as const;

export function QuickAsk({ className }: { className?: string }) {
  /** Hand any question — an example or a typed one — to the real chat. */
  const openChat = useCallback((question: string) => {
    writeHandoff([], question);
    window.location.href = "/chat";
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    /* Holding the turn: the gallery composer composes a consumer `onSubmit`
       with its own send, and `preventDefault()` is how the digichat embed's
       free-turn gate holds one. Here it also stops the fixture running. */
    event.preventDefault();
    const text = (event.currentTarget.querySelector("textarea")?.value ?? "").trim();
    openChat(text);
  }

  function handleClickCapture(event: MouseEvent<HTMLDivElement>) {
    const row = (event.target as HTMLElement).closest(".aui-thread-welcome-suggestion");
    if (!row) return;
    event.preventDefault();
    event.stopPropagation();
    /* Read the Title slot, not the row: the row also carries the example
       mark's visually-hidden label ("Example"), which is not the question. */
    const title = row.querySelector(".aui-thread-welcome-suggestion-text-1");
    openChat((title?.textContent ?? "").replace(/\s+/g, " ").trim());
  }

  return (
    <div className={className}>
      <div className="flex flex-col gap-[0.7rem]">
        <div className="flex flex-wrap items-baseline justify-between gap-x-[1rem] gap-y-[0.4rem]">
          <p className={`m-0 ${GROUPED_LABEL}`}>digichat</p>
          <p className="m-0 font-mono text-[0.68rem] text-ink-mute">
            example turns · a question opens the real chat
          </p>
        </div>
        <div
          className="aui-theme-stage"
          style={STAGE_STYLE}
          onClickCapture={handleClickCapture}
        >
          <DigichatFixtureRuntime suggestions={ASK_SUGGESTIONS}>
            <Thread
              autoFocus={false}
              components={THREAD_COMPONENTS}
              placeholder={ASK_PLACEHOLDER}
              composerLayout="compact"
              onComposerSubmit={handleSubmit}
            />
          </DigichatFixtureRuntime>
        </div>
      </div>
    </div>
  );
}
