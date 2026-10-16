"use client";

import { m, useMotionValueEvent, useScroll } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useMotionSafe } from "../../motion/primitives";

/**
 * TypewriterReveal — the copy types itself out as the line rides up the page.
 *
 * The sibling of <WordReveal/> and <MotionReveal/>, and the third answer to the
 * same question: how does long copy earn attention on scroll?
 *
 *   <WordReveal/>     pinned, 150vh of track, words fill from blur. One per page.
 *   <MotionReveal/>   unpinned, words deepen in colour in order. Supporting claims.
 *   <TypewriterReveal/> unpinned, characters appear in order, with a caret.
 *
 * Not pinned, and that is deliberate: a typed quote that held the viewport for a
 * screen and a half would be a performance the reader has to wait out. This one
 * types as the line travels, so the page never stops, and it finishes around
 * mid-viewport.
 *
 * **Layout.** Revealing characters would normally reflow the paragraph on every
 * tick, so the full text is laid out once in a hidden ghost and the typed copy is
 * drawn over it. The box is therefore the size of the finished quote from the
 * first frame — nothing on the page below ever moves.
 *
 * **Accessibility.** The visual layers are `aria-hidden`; the full text is
 * exposed once, in a visually-hidden node. So a screen reader reads the finished
 * quote, never a partial one, and the caret is decorative throughout.
 *
 * **Fallbacks.** Under `prefers-reduced-motion` — or with no JS — the component
 * renders the whole line, untyped and without a caret. `useMotionSafe()`, not a
 * raw media-query read: SSR cannot know the preference, so the server pass always
 * takes the plain branch and the real one resolves a tick later (the same
 * hydration-safe pattern as its siblings, #2244).
 *
 * Wiring (in the consuming app): the word-reveal sheet carries this component's
 * few rules too —
 *   globals.css  @import "@digithings/ui/styles/word-reveal.css";
 */

/** Where in the element's travel the typing runs. */
const REVEAL_START = 0.04;
const REVEAL_END = 0.72;

export type TypewriterRevealProps = {
  /** The copy to type out. */
  text: string;
  /** Extra classes on the inline wrapper. */
  className?: string;
};

export function TypewriterReveal({ text, className }: TypewriterRevealProps) {
  const trackRef = useRef<HTMLSpanElement | null>(null);
  const safe = useMotionSafe();
  // 0 when the line's top reaches the bottom edge of the viewport, 1 once its
  // bottom has climbed to the middle. Starting at the element's first pixel of
  // visibility is what keeps the collapse from the full copy to an empty one
  // off-screen, so a reader never sees the text vanish and retype.
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start end", "end center"],
  });
  // The server — and the first client frame — render the whole line, so there is
  // never a blank quote in the HTML and nothing to hydrate-mismatch against.
  const [shown, setShown] = useState(text.length);

  const advance = useCallback(
    (progress: number) => {
      const travel = Math.max(0.0001, REVEAL_END - REVEAL_START);
      const t = Math.min(1, Math.max(0, (progress - REVEAL_START) / travel));
      setShown(Math.round(t * text.length));
    },
    [text.length],
  );

  // Read the current position once on mount as well as on every change: a line
  // that is already past its reveal window when the page loads should be whole,
  // not waiting for a scroll that may never come.
  useEffect(() => {
    advance(scrollYProgress.get());
  }, [advance, scrollYProgress]);

  useMotionValueEvent(scrollYProgress, "change", advance);

  const typed = safe ? text.slice(0, shown) : text;
  const typing = safe && shown < text.length;

  return (
    <m.span ref={trackRef} className={`tw${className ? ` ${className}` : ""}`}>
      <span className="tw-ghost" aria-hidden="true">
        {text}
      </span>
      <span className="tw-live" aria-hidden="true">
        {typed}
        {typing ? <span className="tw-caret" /> : null}
      </span>
      <span className="tw-sr">{text}</span>
    </m.span>
  );
}
