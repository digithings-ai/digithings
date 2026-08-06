"use client";

import type { ReactNode } from "react";
import { TerminalStepCaret } from "./step-caret";

/**
 * Container-boot loader — the full-surface wait shown while the app's
 * container is still coming up. A scale-to-zero container answers its first
 * request in 15–25s, and a spinner spends all of it saying nothing; this says
 * which phase is running, in the house type-out: the step label types out at
 * the brand's block cursor, holds, deletes, and the next one follows.
 *
 * The composition is a terminal line caught mid-prompt — wordmark, hairline,
 * the typing step, and one quiet note setting the expectation — left-aligned
 * on a mono grid and centred in the surface. It carries **no** mark before the
 * label: word plus block cursor is the lockup itself, and the mark is what
 * makes this read as the brand rather than as a progress widget.
 *
 * The steps are a script, not telemetry: nothing can report progress from
 * inside a container that has not started. So they default to the phases of an
 * ordinary cold start and the last one HOLDS (`loop={false}`) — a boot screen
 * that loops back to step one reads as stuck. Pass `steps` to name the real
 * phases, or `activeIndex` once something outside the container can report
 * them (a health-check poller, a readiness probe).
 *
 * One motion moment: the caret. No spinner, no progress rail, no counter.
 * `prefers-reduced-motion` shows the first step's label whole with the caret
 * still — see <TerminalStepCaret>. Frame styles: `.tl-boot*` in terminal.css.
 */
export type ContainerBootLoaderProps = {
  /** Boot phases, in order. Defaults to an ordinary cold start. */
  steps?: string[];
  /** Caller-driven phase; omit to run the script on the internal clock. */
  activeIndex?: number;
  /** Brand line above the rule — typically a wordmark. Omit for none. */
  title?: ReactNode;
  /** The expectation-setting line under the caret. Pass `null` to drop it. */
  note?: ReactNode;
  /** Pin to the viewport — the usual mode, over a not-yet-rendered app. */
  fullscreen?: boolean;
  className?: string;
};

/** The phases of an ordinary cold start. Illustrative — name your own. */
const BOOT_STEPS = [
  "waking the container",
  "booting the chat surface",
  "linking digigraph",
  "restoring your session",
  "warming the model runtime",
];

const BOOT_NOTE = "cold start · the container sleeps when idle";

export function ContainerBootLoader({
  steps = BOOT_STEPS,
  activeIndex,
  title,
  note = BOOT_NOTE,
  fullscreen = false,
  className,
}: ContainerBootLoaderProps) {
  return (
    <div
      className={["tl-boot", fullscreen ? "is-fixed" : "", className ?? ""]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="tl-boot-inner">
        {title ? <p className="tl-boot-title">{title}</p> : null}
        <hr className="tl-boot-rule" />
        <TerminalStepCaret steps={steps} activeIndex={activeIndex} loop={false} />
        {note ? <p className="tl-note">{note}</p> : null}
      </div>
    </div>
  );
}

export { BOOT_STEPS as CONTAINER_BOOT_STEPS };
