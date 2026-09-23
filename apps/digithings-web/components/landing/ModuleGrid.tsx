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
import { moduleLines } from "@/lib/repoActivity";

/**
 * The module mosaic (v15, #4429), and the page's `#architecture` anchor.
 *
 * The anchor used to live on a heading above the mosaic — "Every module, one at
 * a time". The owner removed the title, so the id moved here: the nav and the
 * footer's `/#architecture` link still resolves, and it now lands the reader on
 * the mosaic itself rather than on a heading over it.
 *
 * The owner's v13 ask was a grid of angular boxes that "hooks onto the scroll":
 * a box comes into focus, gains detail, and the focus walks on. The detail is
 * *inside* the focused cell, so the whole story stays in one view and a
 * navigator is unnecessary.
 *
 * The mechanical half is `useScrollyFeatures`: it owns the pinned-track
 * progress mapping and, on a small viewport or under
 * `prefers-reduced-motion: reduce`, flips to `stepper` so every module renders
 * in plain flow — no pin, no scrub.
 *
 * v1 set `flex-basis: 30rem` on the focused cell inside a *wrapping* flex row,
 * so growing one cell pushed its neighbours into the next row and the grid
 * re-shaped as the focus advanced. v2 fixed that by pinning every cell to an
 * explicit `grid-template-areas` slot, but a pinned slot cannot also grow, so
 * the focused cell's tagline, stack chips and compose command were cut off —
 * the owner's "we're not resizing them and shifting them around to make space
 * for what's inside of each tile".
 *
 * v3 (this version) does both, and it rests on one observation: **a tile is one
 * grid row tall, always, and only its width carries meaning.**
 *
 * Sizing a tile's *area* instead — a width and a height each — is what produced
 * cells one, two and three rows tall sitting side by side: no two neighbours
 * shared a baseline, the box ran past its own height, and the last two modules
 * wrapped onto a second screen. With every tile exactly one row tall, rows
 * always line up and nothing can overflow, and `width x the shared row height`
 * still makes a tile's area proportional to its width.
 *
 * The spans are apportioned against the *whole* grid, not per row. Normalising
 * each row separately looks equivalent and is not: a row holding three modules
 * gives each of them a bigger share than a row holding four, so digivault
 * (5,003 lines) drew a five-column tile beside digiquant's (178,909 lines)
 * three. Apportioning globally keeps the printed figure and the tile size in
 * the same order.
 *
 * A global apportionment does not by itself pack into whole rows — the remainder
 * leaves one- and two-column gaps that `dense` cannot backfill, because the
 * narrowest tile is two columns wide, and the leftovers spill onto a fourth row.
 * So the spans are then *placed* into exactly `ROWS` rows of exactly `COLS` by a
 * backtracking partition, and each tile is positioned explicitly. That is what
 * makes the box flush at every focus rather than only on average.
 *
 * Finally the layout re-solves for the focused module: its weight is multiplied
 * by `FOCUS_BOOST`, so it takes the widest tile and its neighbours cede that
 * room and re-flow. That is the "shifting them around" the owner asked for, and
 * because the spans still sum to the whole grid the box stays a flush rectangle
 * at every focus.
 */

const ordered = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);

const COLS = 12;
const ROWS = 3;
/** No tile is narrower than this — a one-column tile wraps its own name. */
const MIN_SPAN = 2;
/** No tile is wider than this, so a boosted focus can always share its row. */
const MAX_SPAN = 10;
/** The exponent on the normalised log weight. >1 spreads the field. */
const WEIGHT = 1.2;
/**
 * The share of the biggest module the smallest still draws, before weighting.
 * 0.35 spreads the field about 2.9x end to end, which is the strongest size
 * difference a reader can still compare at a glance without the smallest tile
 * becoming a sliver.
 */
const WEIGHT_FLOOR = 0.35;
/**
 * How much heavier the focused module counts while the layout is solved — this
 * is the "resize and shift to make space for what's inside" behaviour. The
 * focused tile takes the widest span in its row so its tagline, stack chips and
 * compose command have room.
 */
const FOCUS_BOOST = 2.6;

export { COLS as MOSAIC_COLS };

const VH_PER_MODULE = 60;

type Placement = { row: number; col: number; span: number };

/**
 * Each module's size weight, on a log axis.
 *
 * The spread is extreme — digiquant is 178,909 lines and digismith is 951, a
 * factor of 188 — so a linear weight would make digismith a sliver and
 * digiquant most of the grid. On a log axis the ratio is about 1:2.9, which is
 * still legible as "bigger module, bigger tile".
 *
 * The floor matters: without it the smallest module normalises to zero and an
 * earlier attempt's `|| 1` fallback promoted it, so the *smallest* module in
 * the stack drew the widest tile. The floor is applied before the exponent so
 * no module can ever reach zero.
 */
function moduleWeights(): number[] {
  const measured = ordered
    .map((m) => moduleLines(m.id))
    .filter((n): n is number => n !== null);
  const logMin = Math.min(...measured.map((n) => Math.log10(n)));
  const logMax = Math.log10(Math.max(...measured));
  const span = Math.max(logMax - logMin, 1);
  return ordered.map((m) => {
    const n = moduleLines(m.id);
    if (n === null) return WEIGHT_FLOOR;
    const t = (Math.log10(n) - logMin) / span;
    return WEIGHT_FLOOR + (1 - WEIGHT_FLOOR) * Math.pow(t, WEIGHT);
  });
}

const BASE_WEIGHTS = moduleWeights();

/**
 * The column span for every module at a given focus, against the whole grid.
 *
 * Largest-remainder apportionment over `COLS * ROWS` cells gets the total exact
 * by construction. The focused module's boosted share can ask for more than a
 * whole row, so the widest tiles are then capped at `MAX_SPAN` and the freed
 * columns handed to the narrowest tiles — that keeps the total and stops one
 * tile swallowing the grid.
 *
 * Pure in `(weights, focus)`, so the same focus always draws the same mosaic
 * and the same focus always prints the figure that size was derived from.
 */
function solveSpans(focus: number): number[] {
  const weights = BASE_WEIGHTS.map((w, i) => (i === focus ? w * FOCUS_BOOST : w));
  const total = weights.reduce((a, w) => a + w, 0) || 1;
  const budget = COLS * ROWS;
  const exact = weights.map((w) => (budget * w) / total);
  const spans = exact.map(Math.floor);

  let left = budget - spans.reduce((a, s) => a + s, 0);
  const order = exact
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac);
  for (const { i } of order) {
    if (left <= 0) break;
    spans[i] += 1;
    left -= 1;
  }

  let freed = 0;
  for (let i = 0; i < spans.length; i += 1) {
    if (spans[i] > MAX_SPAN) {
      freed += spans[i] - MAX_SPAN;
      spans[i] = MAX_SPAN;
    }
  }
  let guard = 0;
  while (freed > 0 && guard < budget) {
    guard += 1;
    let narrowest = -1;
    for (let i = 0; i < spans.length; i += 1) {
      if (spans[i] >= MAX_SPAN) continue;
      if (narrowest === -1 || spans[i] < spans[narrowest]) narrowest = i;
    }
    if (narrowest === -1) break;
    spans[narrowest] += 1;
    freed -= 1;
  }

  for (let i = 0; i < spans.length; i += 1) if (spans[i] < MIN_SPAN) spans[i] = MIN_SPAN;
  while (spans.reduce((a, s) => a + s, 0) > budget) {
    let widest = -1;
    for (let i = 0; i < spans.length; i += 1) {
      if (spans[i] <= MIN_SPAN) continue;
      if (widest === -1 || spans[i] > spans[widest]) widest = i;
    }
    if (widest === -1) break;
    spans[widest] -= 1;
  }

  return spans;
}

/**
 * Place the spans into exactly `ROWS` rows of exactly `COLS` columns.
 *
 * Tiles are placed widest first and each is dropped into the first row with
 * room for it, with the empty-unused-row symmetry broken so equivalent
 * orderings are not re-searched. That is a backtracking subset-sum over three
 * bins — trivial at eleven tiles, and it either fills every row exactly or
 * reports that it cannot.
 *
 * When it cannot (only reachable if the spans are unusually lumpy) the tiles
 * fall back to first-fit in reading order and an extra row is allowed to exist;
 * the stylesheet gives implicit rows a share of the same fixed height, so the
 * box still cannot overflow its stage.
 */
function packGrid(spans: number[]): Placement[] {
  const order = spans.map((s, i) => ({ i, s })).sort((a, b) => b.s - a.s);
  const bins: number[][] = Array.from({ length: ROWS }, () => []);
  const used = new Array<number>(ROWS).fill(0);
  const placements = new Array<Placement>(spans.length);

  const place = (k: number): boolean => {
    if (k === order.length) return used.every((u) => u === COLS);
    const { i, s } = order[k];
    for (let b = 0; b < ROWS; b += 1) {
      if (b > 0 && bins[b - 1].length === 0) break;
      if (used[b] + s > COLS) continue;
      bins[b].push(i);
      used[b] += s;
      if (place(k + 1)) return true;
      bins[b].pop();
      used[b] -= s;
    }
    return false;
  };

  if (place(0)) {
    bins.forEach((bin, row) => {
      let col = 1;
      for (const index of bin) {
        placements[index] = { row: row + 1, col, span: spans[index] };
        col += spans[index];
      }
    });
    return placements;
  }

  const caps = new Array<number>(ROWS).fill(COLS);
  for (let index = 0; index < spans.length; index += 1) {
    let row = caps.findIndex((cap) => cap >= spans[index]);
    if (row === -1) {
      row = caps.length;
      caps.push(COLS);
    }
    placements[index] = { row: row + 1, col: COLS - caps[row] + 1, span: spans[index] };
    caps[row] -= spans[index];
  }
  return placements;
}

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
      <section id="architecture">
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
      </section>
    );
  }

  const placements = packGrid(solveSpans(Math.max(activeIndex, 0)));

  return (
    <section id="architecture">
      <div ref={trackRef} style={{ height: `${scrollyTrackHeightVh(ordered.length, VH_PER_MODULE)}vh` }}>
        <div className="dg-stage">
          <div
            className="dg-mosaic dg-mosaic--grid"
            style={{ "--cols": COLS, "--rows": ROWS } as React.CSSProperties}
            role="list"
            aria-label="digithings modules, sized by lines of code"
          >
            {ordered.map((m, i) => {
              const on = i === activeIndex;
              const lines = moduleLines(m.id);
              const at = placements[i];
              return (
                <button
                  key={m.id}
                  type="button"
                  role="listitem"
                  className={`dg-cell${on ? " on" : ""}`}
                  style={
                    {
                      gridColumn: `${at.col} / span ${at.span}`,
                      gridRow: at.row,
                    } as React.CSSProperties
                  }
                  aria-current={on ? "true" : undefined}
                  aria-label={
                    lines === null
                      ? `${m.id} — ${m.role}, on the roadmap`
                      : `${m.id} — ${m.role}, ${lines.toLocaleString("en-US")} lines`
                  }
                  onClick={() => ask(m.id)}
                >
                  <span className="dg-mosaic-name">
                    <span className="text-ink-mute">digi</span>
                    {m.id.replace(/^digi/, "")}
                  </span>
                  <span className="dg-mosaic-role">{m.role}</span>
                  <span className="dg-loc">
                    {lines === null ? "roadmap" : `${lines.toLocaleString("en-US")} lines`}
                  </span>

                  {on ? (
                    <span className="dg-mosaic-detail">
                      <span className="dg-mosaic-tag">{m.tagline}</span>
                      {/* Four chips, icon-only: the same dense treatment the kit
                          already uses in the graph's chrome (`chrome.tsx`). A
                          tile is one grid row tall, so the named chips wrapped
                          onto three lines and clipped the compose command on the
                          smallest modules — the owner's "I don't fully see what's
                          inside of each one". */}
                      <StackRow items={m.stack.slice(0, 4)} className="stack-row compact" />
                      <span className="dg-mosaic-foot">
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
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
