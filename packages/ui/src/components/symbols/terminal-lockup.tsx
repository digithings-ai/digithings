/**
 * Animated brand lockup — `digi` and a cursor that types each module in turn.
 *
 * The identity as a live terminal line: `digi` holds, the cursor blinks, then a
 * module suffix types in character by character, holds long enough to read,
 * deletes, and the next one follows. Pure CSS, no JavaScript and no state — so it
 * renders identically on the server and degrades correctly.
 *
 * Suffixes default to the real module registry (`data/modules`) with the shared
 * `digi` prefix stripped, so the animation cannot drift out of sync with the
 * stack the way a hardcoded list would.
 *
 * Two implementation details that are load-bearing:
 *
 * - **Keyframe offsets must be unique and strictly increasing, and every segment
 *   needs its own `animation-timing-function`.** Browsers merge duplicate-offset
 *   keyframes and silently drop the timing function — which turns the
 *   character-by-character type-in into a smooth width slide with no error
 *   anywhere. That is why the offsets are computed rather than hand-written.
 * - **Typing is priced per character, not per slot.** A fixed slot makes a
 *   3-letter module type at 2x the speed of a 6-letter one and the rhythm limps.
 *   Constant cadence means unequal slots, so the shared cycle is built from
 *   cumulative times.
 *
 * The keyframes are emitted as a scoped `<style>` rather than shipped in a family
 * sheet because they are derived from the word list: a static sheet would have to
 * hardcode a module count, and would go stale the moment the registry changes.
 *
 * `prefers-reduced-motion` renders the final state — `digi` + the first module,
 * cursor still — per the canon's one-motion-moment rule.
 */
"use client";

import { useId } from "react";
import { modules } from "../../data/modules";

/** Module suffixes, `digi` stripped: ["graph", "quant", …]. */
export const MODULE_SUFFIXES: string[] = modules
  .map((m) => m.id)
  .filter((id) => id.startsWith("digi"))
  .map((id) => id.slice(4));

/** Seconds. Typing is per character so every module types at one cadence. */
const TYPE_S = 0.14;
const ERASE_S = 0.09;
const HOLD_S = 2.4;
const REST_S = 1.2;

type Phase = { word: string; type: number; hold: number; erase: number; rest: number };

function plan(words: string[]): { phases: Phase[]; total: number } {
  let t = 0;
  const phases: Phase[] = [];
  for (const word of words) {
    const n = word.length;
    const type = t;
    const hold = type + n * TYPE_S;
    const erase = hold + HOLD_S;
    const rest = erase + n * ERASE_S;
    phases.push({ word, type, hold, erase, rest });
    t = rest + REST_S;
  }
  return { phases, total: t };
}

function keyframes(scope: string, words: string[]): string {
  const { phases, total } = plan(words);
  const pct = (s: number) => ((s / total) * 100).toFixed(4);
  return phases
    .map(({ word, type, hold, erase, rest }, i) => {
      const n = word.length;
      const rows: string[] = [];
      if (type > 0) {
        rows.push(`0%{width:0;animation-timing-function:linear}`);
        rows.push(`${pct(type)}%{width:0;animation-timing-function:steps(${n},end)}`);
      } else {
        rows.push(`0%{width:0;animation-timing-function:steps(${n},end)}`);
      }
      rows.push(`${pct(hold)}%{width:${n}ch;animation-timing-function:linear}`);
      rows.push(`${pct(erase)}%{width:${n}ch;animation-timing-function:steps(${n},end)}`);
      rows.push(`${pct(rest)}%{width:0;animation-timing-function:linear}`);
      if (rest < total) rows.push(`100%{width:0}`);
      return `@keyframes ${scope}-t${i}{${rows.join("")}}`;
    })
    .join("");
}

export interface AnimatedLockupProps {
  /** Suffixes to cycle. Defaults to the module registry. */
  suffixes?: string[];
  /** Text before the typed suffix. */
  prefix?: string;
  className?: string;
  /** Accessible name. The typed suffixes are decorative — one name for the whole. */
  title?: string;
}

export function AnimatedLockup({
  suffixes = MODULE_SUFFIXES,
  prefix = "digi",
  className,
  title = "digithings",
}: AnimatedLockupProps) {
  // useId keeps the keyframe names unique if the lockup is ever mounted twice.
  const scope = `dtl${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const { total } = plan(suffixes);
  const css = [
    `.${scope}{font-family:var(--font-mono);font-weight:400;line-height:1.05;`,
    `letter-spacing:0;white-space:nowrap;display:inline-block;user-select:none}`,
    `.${scope} i{font-style:normal;display:inline-block;overflow:hidden;width:0;`,
    `vertical-align:bottom;animation-duration:${total.toFixed(2)}s;`,
    `animation-iteration-count:infinite;animation-fill-mode:both}`,
    suffixes.map((_, i) => `.${scope} i:nth-child(${i + 1}){animation-name:${scope}-t${i}}`).join(""),
    `.${scope} u{display:inline-block;width:.6em;height:.71em;background:currentColor;`,
    `text-decoration:none;animation:${scope}-blink 1.05s steps(1) infinite}`,
    `@keyframes ${scope}-blink{50%{opacity:0}}`,
    keyframes(scope, suffixes),
    `@media (prefers-reduced-motion:reduce){`,
    `.${scope} u{animation:none}`,
    `.${scope} i{animation:none;width:0}`,
    `.${scope} i:nth-child(1){width:${suffixes[0]?.length ?? 0}ch}}`,
  ].join("");

  return (
    <span className={[scope, className].filter(Boolean).join(" ")} role="img" aria-label={title}>
      <style>{css}</style>
      {prefix}
      <span aria-hidden="true">
        {suffixes.map((w) => (
          <i key={w}>{w}</i>
        ))}
      </span>
      <u aria-hidden="true" />
    </span>
  );
}
