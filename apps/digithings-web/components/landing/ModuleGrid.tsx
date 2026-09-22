"use client";

import { useRef, useState } from "react";
import {
  StackRow,
  TerminalManifest,
  modules,
  useScrollyFeatures,
  scrollyTrackHeightVh,
  type ModuleNode,
  type TerminalManifestRow,
} from "@digithings/ui";
import { Button } from "@digithings/ui/ui";
import { writeHandoff } from "@/lib/chatHandoff";

/**
 * The module mosaic (v15, #4429).
 *
 * The owner's v13 ask was a grid of angular boxes that "hooks onto the scroll":
 * a box comes into focus, gains detail, and the focus walks on. This is that
 * grid, refined by v15 point 8 — no module logos, no per-tier colouring, no
 * dots-on-a-rail navigator and no separate right-hand panel. The detail is
 * *inside* the focused cell, which grows in place while the rest recede, so the
 * whole story stays in one view and a navigator is unnecessary.
 *
 * The mechanical half is still `useScrollyFeatures`: it owns the pinned-track
 * progress mapping and, on a small viewport or under
 * `prefers-reduced-motion: reduce`, flips to `stepper` so every module renders
 * in plain flow — no pin, no scrub.
 *
 * Each cell's resting size follows its `tier` (core wider than support, wider
 * than roadmap); the active cell takes the remaining room. Content is the
 * shared `modules` registry — the real `tagline`, `stack` and `dockerCmd`.
 */

const ordered = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);

/** Resting flex basis, by importance: core > support > roadmap. */
const BASIS: Record<string, string> = {
  core: "9rem",
  support: "7.5rem",
  roadmap: "6.5rem",
};

/**
 * The focused cell's basis. Set explicitly rather than left to free-space
 * distribution: with eleven cells wrapping into rows, `flex-grow` alone gives
 * the active cell whatever slack its row happens to have, which can leave the
 * detail clipped in a crowded row. A fixed, generous basis makes the focused
 * tile always wide enough to hold its tagline and command.
 */
const FOCUS_BASIS = "30rem";

/**
 * Scroll budget per module, in `vh`.
 *
 * The shared default is 90vh, which for eleven modules pinned the section for
 * ~9,900px — well over half of the page's total height, and the single longest
 * stretch of scrolling on a page whose whole premise is leanness. Because the
 * track is `slideCount * vhPerSlide` tall with a 100vh sticky child, the scroll
 * a reader actually spends per module is `(track - 100) / slideCount`: 90vh
 * bought ~809px per module, 60vh buys ~510px, which still holds the focused
 * cell's tagline, dependency chips and compose command for a comfortable dwell.
 *
 * Passed per-consumer rather than lowered on `scrollyTrackHeightVh` itself:
 * that default is pinned by `scrolly-core.test.ts`, and a pin over taller or
 * fewer slides may legitimately want the longer dwell.
 */
const VH_PER_MODULE = 60;

function buildOutput(m: ModuleNode): string {
  return [m.tagline, "", ...m.summary].join("\n");
}

/**
 * Ask digichat about a module, or the stack. Module scope, not a component
 * closure: the navigation is not derived from render state, which is also what
 * keeps it off the `react-hooks/immutability` rule.
 */
function ask(id: string | null) {
  const q = id
    ? `What does ${id} do, and how do I use it?`
    : "Give me an overview of the digithings stack.";
  writeHandoff([], q);
  window.location.href = "/chat";
}

export function ModuleGrid() {
  const trackRef = useRef<HTMLDivElement>(null);
  const { activeIndex, stepper } = useScrollyFeatures(trackRef, { slideCount: ordered.length });
  const [sel, setSel] = useState<string | null>(null);

  if (stepper) {
    const rows: TerminalManifestRow[] = ordered.map((m) => ({
      id: m.id,
      name: m.id,
      status: m.tier === "roadmap" ? "roadmap" : "online",
      blurb: m.role,
      detail: buildOutput(m),
    }));
    return (
      <TerminalManifest
        className="mx-auto max-w-[980px]"
        prompt="//"
        command="modules"
        meta={`· ${ordered.length} modules`}
        rows={rows}
        namePrefix="digi"
        hint="select a module"
        selectedId={sel}
        onSelect={setSel}
        aria-label="digithings module manifest"
        footer={
          <Button
            type="button"
            variant="outline"
            size="xs"
            className="mt-auto self-end font-mono text-[0.78rem] text-ink-soft"
            onClick={() => ask(sel)}
          >
            ask <span className="text-ink">digi</span>
            <span className="text-accent">chat</span> →
          </Button>
        }
      />
    );
  }

  return (
    <div ref={trackRef} style={{ height: `${scrollyTrackHeightVh(ordered.length, VH_PER_MODULE)}vh` }}>
      <div className="dg-stage">
        <div className="dg-mosaic" role="list" aria-label="digithings modules">
          {ordered.map((m, i) => {
            const on = i === activeIndex;
            return (
              <button
                key={m.id}
                type="button"
                role="listitem"
                className={`dg-mosaic-cell${on ? " on" : ""}`}
                style={{ flexBasis: on ? FOCUS_BASIS : (BASIS[m.tier] ?? "7.5rem") }}
                aria-current={on ? "true" : undefined}
                aria-label={`${m.id} — ${m.role}`}
                onClick={() => ask(m.id)}
              >
                <span className="dg-mosaic-name">
                  <span className="text-ink-mute">digi</span>
                  {m.id.replace(/^digi/, "")}
                </span>
                <span className="dg-mosaic-role">{m.role}</span>

                {on ? (
                  <span className="dg-mosaic-detail">
                    <span className="dg-mosaic-tag">{m.tagline}</span>
                    <StackRow items={m.stack} />
                    {m.dockerCmd ? (
                      <span className="dg-docker">
                        <span className="prompt">$</span> {m.dockerCmd}
                      </span>
                    ) : null}
                    <span className="dg-mosaic-ask">
                      ask <span className="text-ink">digi</span>
                      <span className="text-accent">chat</span> →
                    </span>
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
