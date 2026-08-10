"use client";
/**
 * ChatThinking — the reasoning disclosure promoted from the chatbot reference
 * family (#1418): the model's chain of thought folded into a single chip —
 * caret · dot · label · step count — that expands into an accent-railed step
 * list. `live` pulses the dot while a run is streaming; a finished run reads
 * its label at rest ("Thought for 4.2s"). Steps reveal one by one when
 * scrolled into view (`animateIn`); reduced motion renders the whole chain
 * settled. Uncontrolled by default (`defaultOpen`) or controlled via
 * `open`/`onOpenChange`. Pass `steps` for the railed list, or `children` for
 * a custom body (e.g. digichat-ui's single reasoning blob — its
 * ChatActivities `reasoning` kind rebuilds as
 * `<ChatThinking label="reasoning"><pre>{text}</pre></ChatThinking>`).
 * Step text inherits the surrounding transcript font. Chip background/hover,
 * caret art, the pulse, the step rail, and the reveal transitions live in
 * styles/chat-widgets.css (import it once app-wide; see the wiring note
 * there).
 */
import { useRef, useState, type ReactNode } from "react";
import { useInView } from "motion/react";
import { useMotionSafe } from "../../motion/primitives";

export type ChatThinkingProps = {
  /** Chip label, e.g. `Thought for 4.2s` or `Thinking…`. */
  label: ReactNode;
  /** Reasoning steps, revealed down an accent rail. */
  steps?: string[];
  /** Right chip segment; defaults to `${steps.length} steps`. Pass null to hide. */
  count?: ReactNode;
  /** Pulse the dot while the run is live (off under reduced motion). */
  live?: boolean;
  /** Reveal steps as they scroll into view (default true; off under reduced motion). */
  animateIn?: boolean;
  defaultOpen?: boolean;
  /** Controlled open state; omit to let the chip own it. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Custom disclosure body rendered under the chip (instead of / after `steps`). */
  children?: ReactNode;
  className?: string;
};

export function ChatThinking({
  label,
  steps,
  count,
  live = false,
  animateIn = true,
  defaultOpen = false,
  open,
  onOpenChange,
  children,
  className,
}: ChatThinkingProps) {
  const safe = useMotionSafe();
  const [ownOpen, setOwnOpen] = useState(defaultOpen);
  const isOpen = open !== undefined ? open : ownOpen;

  const listRef = useRef<HTMLOListElement | null>(null);
  const inView = useInView(listRef, { amount: 0.4, once: true });
  const animate = animateIn && safe;
  const revealed = !animate || inView;

  const toggle = () => {
    const next = !isOpen;
    if (open === undefined) setOwnOpen(next);
    onOpenChange?.(next);
  };

  const shownCount = count !== undefined ? count : steps ? `${steps.length} steps` : null;

  return (
    <div className={`flex flex-col items-start gap-[0.55rem]${className ? ` ${className}` : ""}`}>
      <button
        type="button"
        className={`think-chip inline-flex cursor-pointer items-center gap-[0.5rem] rounded-full border border-hair px-[0.7rem] py-[0.35rem] font-mono text-[0.7rem] text-ink-mute${
          isOpen ? " open" : ""
        }`}
        aria-expanded={isOpen}
        onClick={toggle}
      >
        <span className="think-caret" aria-hidden="true" />
        <span className={`think-dot${live && safe ? " is-live" : ""}`} aria-hidden="true" />
        {label}
        {shownCount != null ? (
          <span className="ml-[0.1rem] border-l border-hair pl-[0.5rem] text-ink-mute">
            {shownCount}
          </span>
        ) : null}
      </button>

      {isOpen && steps?.length ? (
        <ol
          ref={listRef}
          className={`think-steps m-0 ml-[0.35rem] flex list-none flex-col gap-[0.5rem] p-0 pl-[1.4rem]${
            revealed ? " in" : ""
          }`}
        >
          {steps.map((s, i) => (
            <li
              key={s}
              className="relative text-[0.8rem] leading-[1.5] text-ink-mute"
              style={animate ? { transitionDelay: `${i * 90}ms` } : undefined}
            >
              {s}
            </li>
          ))}
        </ol>
      ) : null}

      {isOpen ? children : null}
    </div>
  );
}
