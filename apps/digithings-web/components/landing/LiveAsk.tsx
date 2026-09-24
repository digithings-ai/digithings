"use client";

import { Button } from "@digithings/ui/ui";
import { ChatEmbedShell } from "@/components/ChatEmbedShell";

/**
 * The FAQ band's right pane: the live digichat embed, in place (#4429).
 *
 * This replaces the round-4..6 `QuickAsk` simulation (fixture runtime, canned
 * answers badged `example`). That box answered where it stood because its
 * transcript lived in-page and could be handed to `/chat`; a live iframe's
 * transcript is cross-origin and unreachable, so the trade is explicit: the
 * conversation here IS the real product (digigraph backend, same `/embed` the
 * `/chat` route frames), and the expand control opens `/chat` fresh rather
 * than carrying a transcript over.
 *
 * The frame keeps the simulation's fixed reading height
 * (`clamp(22rem, 40vh, 30rem)`) so the morph geometry in `FaqMorph` is
 * unchanged — `ChatEmbedShell` fills whatever box it is given. The expand
 * control keeps the round-5 overlay pattern (a `pointer-events-none` layer
 * with the button re-enabling its own) because the gallery sheet's
 * `.aui-theme-stage > * { height: 100% }` rule turned a bare overlay button
 * into a full-height column.
 */

const STAGE_STYLE = {
  height: "clamp(22rem, 40vh, 30rem)",
  marginTop: 0,
  background: "var(--surface)",
  position: "relative",
} as const;

export function LiveAsk({ embedOrigin, className }: { embedOrigin: string; className?: string }) {
  function expand() {
    window.location.href = "/chat";
  }

  return (
    <div className={className}>
      <div className="flex flex-col gap-[0.7rem]">
        <div className="aui-theme-stage" style={STAGE_STYLE}>
          <ChatEmbedShell embedOrigin={embedOrigin} />
          <span
            aria-hidden="false"
            className="pointer-events-none absolute inset-0 z-10 flex items-start justify-end p-[0.5rem]"
          >
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={expand}
              aria-label="Open the full chat"
              title="Full screen chat"
              className="pointer-events-auto bg-surface px-[0.5rem] text-ink-soft"
            >
              <span aria-hidden="true" className="text-[0.9rem] leading-none">
                ⤢
              </span>
            </Button>
          </span>
        </div>
      </div>
    </div>
  );
}
