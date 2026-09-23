"use client";

import { useEffect, useRef, useState } from "react";
import {
  StackRow,
  modules,
  useScrollyFeatures,
  scrollyTrackHeightVh,
  type ModuleNode,
} from "@digithings/ui";
import { writeHandoff } from "@/lib/chatHandoff";
import { grouped, moduleLines } from "@/lib/repoActivity";
import { moduleCountLabel, moduleCounts, moduleVersion } from "@/lib/moduleCounts";

/**
 * The module mosaic (v15, #4429), and the page's `#architecture` anchor.
 *
 * The anchor used to live on a heading above the mosaic. The owner removed the
 * title, so the id moved here: the nav and the footer's `/#architecture` link
 * still resolves, and it now lands the reader on the mosaic itself.
 *
 * The owner's ask was a grid of angular boxes that "hooks onto the scroll": a box
 * comes into focus, gains detail, and the focus walks on. The detail is *inside*
 * the focused cell, so the whole story stays in one view.
 *
 * The mechanical half is `useScrollyFeatures`: it owns the pinned-track progress
 * mapping and, on a small viewport or under `prefers-reduced-motion: reduce`,
 * flips to `stepper`. The mosaic then renders as a *stack* rather than a grid —
 * the same boxes, one per row, opening in turn as the reader scrolls, and all
 * open at once under reduced motion where nothing may move.
 *
 * v6 answers the two things the owner found next.
 *
 * **Fit.** The focused tile rendered every summary paragraph, so on the modules
 * with the longest copy (digigraph, digivault) the compose command and the ask
 * control were pushed past the box's edge and clipped. The copy block is now the
 * only part allowed to shrink, the stack row and the foot are pinned, and the
 * lead paragraph is line-clamped — so the controls are always visible.
 *
 * **Mobile.** `stepper` used to render `TerminalManifest` (a list you click to
 * print a module's text). The owner wants the boxes kept on a phone, stacked, and
 * opening sequentially as you scroll. The stack is the same tile markup with one
 * tile per row, so there is a single tile to maintain and the two faces cannot
 * drift apart.
 *
 * v4 (this version) fixes the two things the owner found in the walkthrough.
 *
 * **Order.** v3 solved the sizes with `solveSpans` + `packGrid`, and `packGrid`
 * placed tiles widest-first (`sort((a, b) => b.s - a.s)`) to make the rows pack
 * flush. That silently made the *reading order* a function of tile size: at one
 * focus the first row read digigraph -> digisearch, while `graphOrder` is
 * digigraph -> digiquant. Worse, it re-solved on every focus step, so the tiles
 * swapped places as the scroll advanced. The owner's rule is the opposite — the
 * order is fixed and only the sizes move.
 *
 * **Motion.** There was none. Placement was two explicit grid lines per tile, and
 * a `grid-column` span is not interpolable, so every focus step was a jump. The
 * owner wants the focused tile to grow while its neighbours shrink to make room,
 * which is exactly what `flex-grow` does natively.
 *
 * So the mosaic is a flex layout now, and its shape is decided at module scope:
 *
 *   - eleven tiles split into three fixed rows in `graphOrder` (4 / 4 / 3), so a
 *     tile can never move between rows and reading order is permanent;
 *   - rows are flex items of a column container, each growing in proportion to
 *     its members' weight, so the row holding the focused tile grows and the
 *     other two cede height;
 *   - tiles are flex items of their row, each growing in proportion to its own
 *     log weight, multiplied by `FOCUS_BOOST` while focused, so the focused tile
 *     grows and its row-mates shrink proportionally;
 *   - both levels animate `flex-grow`, and a tile's width is `flex-grow` share x
 *     the row width, so the rows are flush by construction — the property v3
 *     needed a backtracking partition to reach.
 *
 * v5 gives the tile its facts and its own interactions. A tile used to route to
 * `/chat` on click, which conflated "tell me about this module" with "open the
 * assistant". The click now moves the scroll to that module's step — the same
 * focus the scroll already drives, just addressed directly — and only the tile's
 * "ask digichat" control navigates. The compose command became a copy control,
 * and the three stated facts (lines of code, endpoints, MCP tools) and the
 * declared version moved out of the corner into a fixed box under the name, so
 * every tile states the same three things in the same order.
 */

const ordered = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);

/** Tiles per row, top to bottom. Fixed, so reading order can never change. */
const ROW_SIZES = [4, 4, 3] as const;

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
 * How much heavier the focused module counts while the layout is solved — the
 * "resize and shift to make space for what's inside" behaviour.
 */
const FOCUS_BOOST = 2.6;
/**
 * The share of the mosaic's height the focused tile's row holds.
 *
 * A flat multiplier on the row's weight is not enough, because the rows' base
 * weights differ by 2.7x: the same multiplier left the focused row in the
 * lighter rows too short for its own detail — measured, digismith's clipped by
 * 34px. Solving for the multiplier that reaches this share instead makes the
 * guaranteed height the same wherever the focus lands.
 *
 * The floor of 1 on the multiplier matters: the heaviest row is already above
 * this share with no boost at all, and a share below the weight it would hold
 * anyway must not shrink it.
 */
const ROW_FOCUS_SHARE = 0.56;
/**
 * The least height any row keeps, as a share of the mosaic.
 *
 * The rows' base weights differ by 2.7x, so a strongly boosted focused row left
 * the lightest row too short for even a resting tile's name, figures, role and
 * chips — measured, a 7px clip on digivault. A floor here is cheaper and more
 * honest than trimming a tile that has nothing left to trim.
 */
const ROW_MIN_SHARE = 0.19;

const VH_PER_MODULE = 60;

/**
 * The stacked face's focal line, as a share of the viewport height. The tile
 * whose top sits nearest this line is the one that opens, so the open tile
 * tracks the reader's eye rather than the viewport edge.
 */
const STACK_FOCAL = 0.38;

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/**
 * Whether the reader asked for reduced motion. SSR cannot know the media query,
 * so the first client render reports `false` to match the server markup and the
 * real preference resolves one effect-tick later — the same hydration-safe shape
 * as the kit's `useMotionSafe` (#2244).
 */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(REDUCED_MOTION_QUERY);
    const apply = () => setReduced(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return reduced;
}

/**
 * Each module's size weight, on a log axis.
 *
 * The spread is extreme — digiquant is 178,909 lines and digismith is 951, a
 * factor of 188 — so a linear weight would make digismith a sliver and digiquant
 * most of the mosaic. On a log axis the ratio is about 1:2.9, which is still
 * legible as "bigger module, bigger tile".
 *
 * The floor matters: without it the smallest module normalises to zero and an
 * earlier attempt's `|| 1` fallback promoted it, so the *smallest* module in the
 * stack drew the widest tile. The floor is applied before the exponent so no
 * module can ever reach zero.
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

/** Row index -> the members' indices into `ordered`. Fixed at module scope. */
const ROWS: number[][] = (() => {
  const rows: number[][] = [];
  let cursor = 0;
  for (const size of ROW_SIZES) {
    rows.push(ordered.slice(cursor, cursor + size).map((_, k) => cursor + k));
    cursor += size;
  }
  return rows;
})();

/** Which row a tile sits in. */
const ROW_OF = (() => {
  const map = new Array<number>(ordered.length).fill(0);
  ROWS.forEach((members, row) => members.forEach((i) => (map[i] = row)));
  return map;
})();

/**
 * The stacked face: the same tiles in the same order, one per row.
 *
 * The mosaic is a fixed 4/4/3 outline, which needs width to read as a mosaic.
 * On a phone there is none, so the rows become single-tile rows and the column
 * grows with its content — the boxes stack, and only the active one is open.
 */
const STACK_ROWS: number[][] = ordered.map((_, i) => [i]);

/**
 * The flex-grow value for every tile at a given focus. Pure in `(weights,
 * focus)`, so the same focus always draws the same mosaic.
 */
function solveTileGrow(focus: number): number[] {
  return BASE_WEIGHTS.map((w, i) => (i === focus ? w * FOCUS_BOOST : w));
}

/**
 * The flex-grow value for every row: the sum of its members' unboosted weights,
 * with the focused row's lifted until it holds `ROW_FOCUS_SHARE` of the height.
 * Unboosted members are deliberate — the tile boost already widens the focused
 * tile inside the row; boosting the row on top of that would double-count the
 * same emphasis.
 */
function solveRowGrow(focus: number): number[] {
  const sums = ROWS.map((members) => members.reduce((acc, i) => acc + BASE_WEIGHTS[i], 0));
  const focused = ROW_OF[focus];
  const total = sums.reduce((acc, sum) => acc + sum, 0);
  /* The heaviest row is already past the target, so its own share stands in. */
  const focusShare = Math.max(ROW_FOCUS_SHARE, sums[focused] / total);
  const rest = 1 - focusShare;

  const others = sums.map((sum, row) => (row === focused ? 0 : sum));
  const otherTotal = others.reduce((acc, sum) => acc + sum, 0) || 1;
  const starving = sums.map(
    (sum, row) => row !== focused && (rest * sum) / otherTotal < ROW_MIN_SHARE,
  );
  const floored = starving.filter(Boolean).length * ROW_MIN_SHARE;
  const flexible = rest - floored;
  const flexibleTotal = sums.reduce(
    (acc, sum, row) => (starving[row] ? acc : acc + others[row]),
    0,
  );

  return sums.map((sum, row) => {
    if (row === focused) return focusShare;
    if (starving[row]) return ROW_MIN_SHARE;
    return flexibleTotal > 0 ? (flexible * others[row]) / flexibleTotal : ROW_MIN_SHARE;
  });
}

/** One line per module for the terminal manifest and the tile's accessible name. */
function factsLine(m: ModuleNode): string {
  const lines = moduleLines(m.id);
  const counts = moduleCountLabel(m.id);
  return [lines === null ? "roadmap" : `${grouped(lines)} lines`, counts]
    .filter(Boolean)
    .join("  ·  ");
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

/**
 * Move the page so `index` is the step the scrolly pin is showing.
 *
 * `useScrollyFeatures` maps window scroll across the track's `start start` ..
 * `end end` span onto the slides, so the inverse is exact: the centre of step
 * `index` sits at `(index + 0.5) / count` of that span. Scrolling there — not
 * routing — is what makes a tile click mean "focus this module": `activeIndex`
 * follows the scroll and the tile grows as if the reader had scrolled to it. The
 * half-step lands mid-dwell, so the active index is unambiguous at both edges.
 *
 * The jump is INSTANT (`behavior: "auto"`), not smooth. `activeIndex` is derived
 * from the scroll position, so a smooth scroll means the index *walks* through
 * every module between the one you left and the one you clicked — each tile
 * taking focus in turn, which reads as the page scrolling itself instead of
 * responding. An instant jump lands on the target index in one step, so exactly
 * one tile animates, which is the zoom the click is meant to mean. (Owner:
 * "when you click the module box, it's ... going through the full scroll
 * animation instead of just skipping and jumping to it.")
 *
 * Module scope and pure in `(element, index)` — it reads no render state — for
 * the same reason `ask` is: it must stay off the `react-hooks/immutability` rule.
 */
function focusModule(track: HTMLElement | null, index: number) {
  if (!track) return;
  const top = track.getBoundingClientRect().top + window.scrollY;
  const span = Math.max(track.offsetHeight - window.innerHeight, 1);
  const target = top + ((index + 0.5) / ordered.length) * span;
  window.scrollTo({ top: Math.max(target, 0), behavior: "auto" });
}

/**
 * Copy text, preferring the async Clipboard API and falling back to a hidden
 * textarea + `execCommand` where it is absent (an insecure context, a browser
 * without the API, or a permission the page does not hold). Resolves to whether
 * the copy happened, so the caller only flips to "copied" when it truly did — a
 * refused copy must not claim success — and never throws.
 */
async function copyText(text: string): Promise<boolean> {
  const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
  if (clipboard?.writeText) {
    try {
      await clipboard.writeText(text);
      return true;
    } catch {
      /* fall through to the textarea path */
    }
  }
  try {
    const el = document.createElement("textarea");
    el.value = text;
    el.setAttribute("readonly", "");
    el.style.position = "fixed";
    el.style.top = "-9999px";
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
}

export function ModuleGrid() {
  const trackRef = useRef<HTMLDivElement>(null);
  const { activeIndex, stepper } = useScrollyFeatures(trackRef, { slideCount: ordered.length });
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const copyTimer = useRef<number | null>(null);
  const reduced = usePrefersReducedMotion();

  /* The stacked face's active tile. The pinned mosaic's focus IS the scroll
     position; the stack has no track to scrub, so the tile whose top sits nearest
     the focal line is the one that opens, recomputed on scroll. */
  const stackRefs = useRef<Array<HTMLElement | null>>([]);
  const [stackActive, setStackActive] = useState(0);

  const copyCommand = (id: string, cmd: string) => {
    void copyText(cmd).then((ok) => {
      if (!ok) return;
      setCopiedId(id);
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopiedId(null), 1400);
    });
  };

  useEffect(() => {
    if (!stepper || reduced) return;
    let raf = 0;
    const pick = () => {
      raf = 0;
      const line = window.innerHeight * STACK_FOCAL;
      let best = 0;
      let bestDistance = Number.POSITIVE_INFINITY;
      stackRefs.current.forEach((el, i) => {
        if (!el) return;
        const distance = Math.abs(el.getBoundingClientRect().top - line);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = i;
        }
      });
      setStackActive(best);
    };
    const onScroll = () => {
      if (raf === 0) raf = window.requestAnimationFrame(pick);
    };
    pick();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf !== 0) window.cancelAnimationFrame(raf);
    };
  }, [stepper, reduced]);

  const focus = Math.max(activeIndex, 0);
  const tileGrow = solveTileGrow(focus);
  const rowGrow = solveRowGrow(focus);
  const rows = stepper ? STACK_ROWS : ROWS;

  return (
    <section id="architecture">
      <div
        ref={trackRef}
        style={
          stepper
            ? undefined
            : { height: `${scrollyTrackHeightVh(ordered.length, VH_PER_MODULE)}vh` }
        }
      >
        <div className={stepper ? "dg-stack-wrap" : "dg-stage"}>
          <div
            className={`dg-mosaic ${stepper ? "dg-mosaic--stack" : "dg-mosaic--rows"}`}
            role="list"
            aria-label="digithings modules, sized by lines of code"
          >
            {rows.map((members, row) => (
              <div
                key={`row-${row}`}
                className="dg-mosaic-row"
                style={stepper ? undefined : ({ flexGrow: rowGrow[row] } as React.CSSProperties)}
              >
                {members.map((i) => {
                  const m = ordered[i];
                  const on = stepper ? reduced || i === stackActive : i === focus;
                  const lines = moduleLines(m.id);
                  const counts = moduleCounts(m.id);
                  const version = moduleVersion(m.id);
                  const dockerCmd = m.dockerCmd;
                  const copied = copiedId === m.id;
                  return (
                    <div
                      key={m.id}
                      ref={
                        stepper
                          ? (el) => {
                              stackRefs.current[i] = el;
                            }
                          : undefined
                      }
                      role="listitem"
                      className={`dg-cell${on ? " on" : ""}`}
                      style={
                        stepper ? undefined : ({ flexGrow: tileGrow[i] } as React.CSSProperties)
                      }
                      aria-current={on ? "true" : undefined}
                    >
                      {/* The whole tile is the focus target, but the focused
                          tile also owns real controls (copy the compose command,
                          ask digichat). A <button> cannot contain another
                          button, so the focus action is a transparent overlay
                          *under* the body rather than the body's parent; the
                          body re-enables pointer events only on its own
                          controls, so every other click falls through to the
                          overlay. Keyboard reach survives: the overlay is the
                          tile's first tab stop, the controls follow. */}
                      <button
                        type="button"
                        className="dg-cell-focus"
                        aria-label={`Focus ${m.id} — ${m.role}, ${factsLine(m)}`}
                        onClick={() =>
                          stepper ? setStackActive(i) : focusModule(trackRef.current, i)
                        }
                      />
                      <div className="dg-cell-body">
                        <span className="dg-mosaic-head">
                          <span className="dg-mosaic-name">
                            <span className="text-ink-mute">digi</span>
                            {m.id.replace(/^digi/, "")}
                          </span>
                          {/* The declared version, top-right. Roadmap modules
                              declare none, so they read "roadmap" rather than a
                              fabricated 0.0.0 — same honesty rule as the counts. */}
                          <span className="dg-loc dg-mosaic-version">
                            {version === null ? "roadmap" : `v${version}`}
                          </span>
                        </span>

                        {/* The three stated facts, stacked under the name in
                            every tile. A module with no value reads "roadmap" or
                            an em dash, never a fabricated zero: null is "does
                            not expose this", not "exposes nothing". */}
                        <span className="dg-stats">
                          <span className="dg-stat">
                            <span className="dg-loc">lines of code</span>
                            <span className="dg-loc dg-stat-v">
                              {lines === null ? "roadmap" : grouped(lines)}
                            </span>
                          </span>
                          <span className="dg-stat">
                            <span className="dg-loc">endpoints</span>
                            <span className="dg-loc dg-stat-v">
                              {counts.endpoints === null ? "—" : counts.endpoints}
                            </span>
                          </span>
                          <span className="dg-stat">
                            <span className="dg-loc">mcp tools</span>
                            <span className="dg-loc dg-stat-v">
                              {counts.mcpTools === null ? "—" : counts.mcpTools}
                            </span>
                          </span>
                        </span>

                        {/* (d) the short summary in a few words. */}
                        <span className="dg-mosaic-role">{m.role}</span>

                        {on ? (
                          <span className="dg-mosaic-detail">
                            {/* (e) the deeper description: the tagline sentence
                                and the module's lead paragraph. The tile is one
                                row tall, and rendering every paragraph pushed the
                                compose command and the ask control out of the box
                                on the modules with the longest copy (digigraph,
                                digivault). So the copy is the one part allowed to
                                shrink and is clamped by CSS, while the stack row
                                and the foot below are pinned — the controls can
                                never be the thing that clips. The rest of the
                                summary is on the module's docs page and in the
                                ask answer. */}
                            <span className="dg-mosaic-copy">
                              <span className="dg-mosaic-tag">{m.tagline}</span>
                              {m.summary[0] ? (
                                <span className="dg-mosaic-serves">{m.summary[0]}</span>
                              ) : null}
                            </span>
                            {/* (f) the packages used. */}
                            <StackRow items={m.stack} className="stack-row compact" />
                            <span className="dg-mosaic-foot">
                              {/* (g) the compose command, click-to-copy. */}
                              {dockerCmd ? (
                                <button
                                  type="button"
                                  className={`dg-docker${copied ? " is-copied" : ""}`}
                                  aria-label={copied ? "Copied" : `Copy command: ${dockerCmd}`}
                                  onClick={() => copyCommand(m.id, dockerCmd)}
                                >
                                  <span className="prompt" aria-hidden="true">
                                    {copied ? "✓" : "$"}
                                  </span>{" "}
                                  {copied ? "copied" : dockerCmd}
                                </button>
                              ) : null}
                              {/* (h) the one control that may navigate. */}
                              <button
                                type="button"
                                className="dg-mosaic-ask"
                                aria-label={`Ask digichat about ${m.id}`}
                                onClick={() => ask(m.id)}
                              >
                                ask <span className="text-ink">digi</span>
                                <span className="text-accent">chat</span> →
                              </button>
                            </span>
                          </span>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
