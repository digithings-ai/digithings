"use client";

import { useCallback, type FormEvent, type MouseEvent } from "react";
import { CtaLink } from "@digithings/ui";
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

/**
 * The stage frame's own height and ground. Inline because both must outrank
 * the sheet.
 *
 * `17rem` is the measured height of the empty cluster — the welcome, its four
 * example rows and the composer come to 259px, and the gallery frame was
 * `min(72vh, 46rem)`, which on this band left ~80px of dead black above the
 * copy (the footer docks to the bottom, so the slack all piles up top). The
 * frame is sized to the thing it contains instead.
 *
 * `--surface` is the panel tone: the app sheet pins the Thread root and its
 * docked footer to the same colour, so the stage reads as one widget set into
 * the page rather than three near-blacks in a stack.
 */
const STAGE_STYLE = {
  height: "17rem",
  marginTop: 0,
  background: "var(--surface)",
} as const;

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
          <p className="m-0 font-mono text-[0.68rem] text-ink-mute">example turns</p>
        </div>
        <div
          /* One panel, not a stack of near-blacks. The gallery sheet is written
             for a full-page specimen where the frame and the page are the same
             ground: `.aui-theme-stage` paints `--bg`, the Thread root paints
             its own terminal `--term-bg` (#08090b) and the docked footer paints
             `--bg` again. Pinning both descendants to the stage's `--surface`
             is the app's call, so it lives here as an arbitrary-variant
             utility rather than a new `.aui-*` rule in the app sheet (which the
             canon guard would read as a new component family). The two-class
             variant outranks the single-class `bg-background` on both. */
          className="aui-theme-stage [&_.aui-thread-root]:bg-surface! [&_.aui-thread-viewport-footer]:bg-surface!"
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
        {/* The way out, said out loud. Clicking an example row or sending from
            the composer already leaves for /chat, but nothing on the box said
            so — the only hint was the micro-caption beside the label. A plain
            link is the affordance for a visitor who would rather not type. */}
        <div className="flex flex-wrap items-center justify-between gap-x-[1rem] gap-y-[0.5rem]">
          <p className="m-0 font-mono text-[0.68rem] text-ink-mute">
            the turns above are canned — ask anything to continue in the real chat
          </p>
          <CtaLink href="/chat" variant="ghost">
            Continue in digichat
          </CtaLink>
        </div>
      </div>
    </div>
  );
}
