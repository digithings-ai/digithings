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
 * a box comes into focus, gains detail, and the focus walks on. The detail is
 * *inside* the focused cell, which grows in place while the rest recede, so the
 * whole story stays in one view and a navigator is unnecessary.
 *
 * The mechanical half is `useScrollyFeatures`: it owns the pinned-track
 * progress mapping and, on a small viewport or under
 * `prefers-reduced-motion: reduce`, flips to `stepper` so every module renders
 * in plain flow — no pin, no scrub.
 *
 * v2 fixes the owner's one real complaint: "the box grid should remain the same
 * size the whole time … the outline stays the same and the sizes change
 * internally". The v1 mosaic set `flex-basis: 30rem` on the focused cell inside
 * a *wrapping* flex row, so growing one cell pushed its neighbours into the next
 * row and the grid visibly re-shaped as the focus advanced. Measured over the
 * eleven steps: the focused cell swung 459px → 628px, the mosaic's height swung
 * 337px → 464px, and the row composition changed at steps 5, 7, 8 and 10.
 *
 * v2 gives each layout an explicit `grid-template-areas` with every cell named
 * and absolute row tracks, so the box is byte-identical at every focus and only
 * the interior moves. Four layouts are built as alternatives (`MOSAIC_LAYOUTS`)
 * for the owner to choose between; `MOSAIC_LAYOUT` selects the live one.
 */

const ordered = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);

/**
 * The four alternative layouts. Each maps the eleven modules to grid areas in
 * reading order, and each is a *different shape of grid* rather than a different
 * animation — the point being that the outline is frozen in all four, so the
 * owner is choosing a composition, not a motion.
 *
 * All four are twelve-column-free except `b`, which is deliberately dense so the
 * comparison includes one field-like layout against three calmer ones.
 */
export const MOSAIC_LAYOUTS = ["a", "b", "c", "d"] as const;
export type MosaicLayout = (typeof MOSAIC_LAYOUTS)[number];

/** Which layout is live. Change this one line to compare. */
const MOSAIC_LAYOUT: MosaicLayout = "a";

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
        <div
          className={`dg-mosaic dg-mosaic--grid dg-mosaic--${MOSAIC_LAYOUT}`}
          role="list"
          aria-label="digithings modules"
        >
          {ordered.map((m, i) => {
            const on = i === activeIndex;
            return (
              <button
                key={m.id}
                type="button"
                role="listitem"
                className={`dg-cell f${i + 1}${on ? " on" : ""}`}
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
