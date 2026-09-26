"use client";

import { useEffect, useRef, useState } from "react";
import {
  Reveal,
  StackRow,
  modules,
  useScrollyFeatures,
  scrollyTrackHeightVh,
  type ModuleNode,
} from "@digithings/ui";
import { writeHandoff } from "@/lib/chatHandoff";
import { treemapAnchored, treemapAreasConstrained, type TreemapMins } from "@/lib/treemap";
import { grouped, moduleLines } from "@/lib/repoActivity";
import { moduleCountLabel, moduleVersion } from "@/lib/moduleCounts";

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
 *  every tile states the same three things in the same order.
 *
 * v16 answers the owner's grid-fill pass: the mosaic is always full stage
 * height — landing fills to the viewport bottom, the walk plays full-size,
 * and the release hands a full-size grid on (no resting/docked two-state, no
 * retraction, no gap before the next section). The weight spread widened
 * (floor 0.12, exponent 1.5, ~8.3x end to end, roadmaps at half floor) so
 * each tile's area reads as its proportionate LOC portion.
 *
 * v17 replaces the v4 fixed rows with a squarified treemap (owner: the
 * focused tile should grow only as much as its content needs, neighbours must
 * keep their proportionate sizes without stretching, and tiles may reflow
 * freely — "it could be a bit more disorganized"). Focusing re-solves the
 * whole partition with a lifted focused weight (a modest multiplier for big
 * tiles, a content-fit floor for small ones), so every tile's area stays its LOC portion at every focus: no row-mate is ever
 * stretched by the focused tile's height, and nothing below is ever
 * compressed by it. Each tile eases to its new rect on a CSS
 * left/top/width/height transition over the brand curve — the kit's motion
 * vocabulary is transform/opacity only, so rect interpolation lives in CSS,
 * driven by motion's `useScroll` walk upstream. The v4 flex-rows description
 * below is history.
 *
 * v18 anchors the focus (owner: "the module that's open should not be
 * rearranged... the module that expands stays"). The rest layout is solved
 * once and never moves; the focused tile keeps its rest top-left and grows
 * there, while the other tiles repack into the strips around it. Within a
 * strip, weight ratios stay exact; global cross-strip proportions are
 * approximate — followability won that trade.
 */

/**
 * Reading order: by size, biggest first — "we have to order the modules based on
 * lines of code. The biggest one should be in the top left." So the mosaic's
 * first tile is its largest module and the last is its smallest, and because the
 * reading order is also the scroll order, the focus walks biggest to smallest.
 *
 * `graphOrder` is only the tie-break, and roadmap modules (which declare no
 * lines) sink to the end rather than sorting as zero — a module with no code is
 * not a module with no size.
 */
const ordered = [...modules].sort((a, b) => {
  const la = moduleLines(a.id);
  const lb = moduleLines(b.id);
  if (la === null && lb === null) return a.graphOrder - b.graphOrder;
  if (la === null) return 1;
  if (lb === null) return -1;
  return lb - la;
});

/** The exponent on the normalised log weight. >1 spreads the field. */
const WEIGHT = 1.5;
/**
 * The share of the biggest module the smallest shipped module still draws,
 * before weighting. 0.12 with the 1.5 exponent spreads the field about 8.3x
 * end to end — the owner wants a stock-grid read (heavyweights top-left,
 * lightweights bottom-right, size gap obvious, each tile's area its
 * proportionate LOC portion), and the focus boost keeps the smallest tile
 * usable wherever the focus lands.
 */
const WEIGHT_FLOOR = 0.12;
/**
 * Roadmap modules declare no lines, so they draw half the floor rather than
 * the floor itself — a module with no code is not a module with no size, but
 * it is honestly smaller than the smallest shipped one. The half step is
 * load-bearing, not cosmetic: the treemap normalises by the total, so ratios
 * hold bit-for-bit — full-floor roadmaps would draw the same rect as
 * digismith and erase its size.
 */
const ROADMAP_WEIGHT = WEIGHT_FLOOR * 0.5;
/**
 * How the focused module's weight is lifted while the layout is solved.
 *
 * Two-sided, because "just big enough to fit" means different things at the
 * two ends of the field: the multiplier keeps big tiles modest (digiquant
 * grows ~13%, not ×2.6 — its detail fits in far less than a doubled share),
 * while the floor guarantees small tiles their content fit (a ×1.3 digismith
 * would still clip its own detail by ~40px, measured). Everything unfocused
 * keeps its exact weight ratio against the rest, so the field holds its
 * proportions while making exactly the space the focus needs. Both numbers
 * were sized by driving all eleven foci in-page until every focused tile's
 * visible content fits with nothing clipped.
 */
const FOCUS_MULT = 1.3;
const FOCUS_FLOOR = 0.5;
/**
 * The owner's floor: every tile stays wide enough for its title + version
 * with padding (the version wraps below the name where the tile is narrow —
 * both fully shown, never clipped), and every focused tile stays large enough
 * for its detail. Mini tiles set the name a notch smaller (full text, never
 * an abbreviation), so 150px clears the longest name plus padding; the
 * version wraps beneath. Focused detail (facts + lead + stack + foot) needs
 * ~300×260, refined per module by live measurement (see needExtra).
 * Minimums are inflated by the gutter at the call site — the solver works in
 * cell space.
 */
const REST_MIN: TreemapMins = { minW: 150, minH: 84 };
const FOCUS_MIN: TreemapMins = { minW: 300, minH: 260 };
/** The gutter between packed tiles, in px — the 0.5rem rhythm as a number, so
 * the render can inset each rect by half. */
const TREEMAP_GAP = 8;

const VH_PER_MODULE = 90;

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
 * factor of 188 — so a linear weight would make digismith a sliver and
 * digiquant most of the mosaic. On a log axis (log10 2.978..5.253, span
 * 2.274) with the floor and exponent above, digiquant draws ~27% of the
 * mosaic's weight and digismith ~3%: still legible as "bigger module, bigger
 * tile", with the size gap obvious.
 *
 * The floor matters: without it the smallest module normalises to zero and an
 * earlier attempt's `|| 1` fallback promoted it, so the *smallest* module in
 * the stack drew the widest tile. The floor is applied before the exponent so
 * no shipped module can ever reach zero; roadmap modules take
 * `ROADMAP_WEIGHT` instead (see its comment).
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
    if (n === null) return ROADMAP_WEIGHT;
    const t = (Math.log10(n) - logMin) / span;
    return WEIGHT_FLOOR + (1 - WEIGHT_FLOOR) * Math.pow(t, WEIGHT);
  });
}

const BASE_WEIGHTS = moduleWeights();

/**
 * The stacked face: the same tiles in the same order, one per row.
 *
 * The mosaic needs width to read as a mosaic. On a phone there is none, so
 * the tiles stack in normal flow and the column grows with its content —
 * the boxes open in turn as the reader scrolls, and all open at once under
 * reduced motion where nothing may move.
 */
const STACK_ROWS: number[][] = ordered.map((_, i) => [i]);

/**
 * The module's stated facts as one line — the tile's only numbers.
 *
 * The owner asked for the three-row figures block to go: "it's a little messy
 * with all the lines of code endpoints and MCP tool accounts. Those could be
 * moved somewhere else." So the figures moved out of every resting tile and out
 * of a three-row block, and into the focused tile as a single mono line — the
 * size is still checkable (the whole mosaic is sized by the first of them), but
 * no tile is a spreadsheet.
 */
function factsLine(m: ModuleNode): string {
  const lines = moduleLines(m.id);
  const counts = moduleCountLabel(m.id);
  return [lines === null ? "roadmap" : `${grouped(lines)} lines`, counts]
    .filter(Boolean)
    .join(" · ");
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
     the focal line is the one that opens, recomputed on scroll. Defaults to the
     first tile (digiquant): at page top the reader has not scrolled, but the
     first card must already read open — the old -1 default left every card shut
     until the reader pushed hard past the top. */
  const stackRefs = useRef<Array<HTMLElement | null>>([]);
  const [stackActive, setStackActive] = useState(0);

  /**
   * The mosaic's default state is unselected: nothing carries the focus until
   * the reader actually arrives — and focus lives ONLY while the mosaic is
   * centered and ready. The `ready` latch flips once the stage box's centre
   * crosses into the viewport's middle third (the sticky pin has taken up and
   * the stage is centred), and flips back off the moment it leaves: scrolled
   * past, above, or entering off-centre, no tile is focused and nothing zooms
   * (owner ship list: "no more zooming on scroll... when table scrolled past /
   * not fullscreen → out of focus, none highlighted"; "zero focus until
   * centered and ready, then focus animation starts"). The old track-top
   * latch fired too early and never released, so tiles grew while arriving
   * and stayed grown after the table left. The mobile stack needs no such
   * gate: it opens its first tile by default and tracks the scroll from
   * mount (see the stack effect below).
   *
   * v16: the gate drives focus ONLY. It used to drive the mosaic's height as
   * well (compact clamp at rest, full stage once centred), which left a dead
   * void under the grid at landing and collapsed the grid as the pin
   * released — the "big gap" before the next section. The mosaic is now
   * always full stage height (see web-theme), so there is nothing to gate:
   * landing fills to the viewport bottom, the walk plays full-size, and the
   * release hands a full-size grid to the section below with no shrink. Gate
   * on the STAGE box, not the mosaic box (the deadlock lesson stands: the
   * mosaic's height WAS the docked state, so gating on it deadlocked —
   * resting centre sat just above the band and ready never fired).
   */
  /* Focus engagement (owner: digiquant lights up only once the grid is fully
     expanded and in view, after a bit more scrolling — not the moment the
     dock engages). The dock is now permanent, so `engaged` adds ~8% of walk
     progress before the first focus lands, then holds until the stage exits. */
  const [engaged, setEngaged] = useState(false);
  const readyRef = useRef(false);
  useEffect(() => {
    let raf = 0;
    const check = () => {
      raf = 0;
      const track = trackRef.current;
      if (!track) return;
      const top = track.getBoundingClientRect().top + window.scrollY;
      const mosaic = track.querySelector(".dg-mosaic");
      if (!mosaic) return;
      /* Gate on the STAGE box, not the mosaic box: the stage is the unit
         that docks (top: nav height, full viewport height), so its centre
         sits mid-viewport whenever docked. The mosaic box can't be the
         metric — its height IS the docked state (resting 459px vs docked
         856px), so gating on it deadlocks: resting centre sits just above
         the band, ready never fires, is-ready never applies, height never
         grows. Measured live: resting centre 323px vs 344px band edge. */
      const stage = track.querySelector(".dg-stage--mosaic");
      const rect = (stage ?? mosaic).getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const center = rect.top + rect.height / 2;
      /* Hysteresis against dock-edge flapping (part of the scroll jitter):
         enter on the middle third, release on a wider skirt, so a centre
         hovering the boundary can't strobe focus and height. */
      const inside = readyRef.current
        ? center > vh * 0.3 && center < vh * 0.7
        : center > vh * 0.33 && center < vh * 0.67;
      readyRef.current = inside;
      const span = Math.max(track.offsetHeight - vh, 1);
      const progress = (window.scrollY - top) / span;
      if (inside && progress > 0.08) setEngaged(true);
      else if (!inside) setEngaged(false);
    };
    const onScroll = () => {
      if (raf === 0) raf = window.requestAnimationFrame(check);
    };
    check();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf !== 0) window.cancelAnimationFrame(raf);
    };
  }, []);

  const copyCommand = (id: string, cmd: string) => {
    void copyText(cmd).then((ok) => {
      if (!ok) return;
      setCopiedId(id);
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopiedId(null), 1400);
    });
  };

  /* The stack tracks the scroll from mount — no arrival gate. The old
     `started` latch (scroll past the track top) left every card shut at page
     top, so digiquant only opened after a hard push past it. */
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

  const focus = engaged ? Math.max(activeIndex, 0) : -1;

  /**
   * Card density tiers (owner: a tile shows whatever fits — and never clips;
   * at least the title and the version always show fully, with padding).
   * Tiers key off measured tile WIDTH and HEIGHT with an 8px hysteresis skirt
   * per dimension so a tile hovering a boundary can't flap between states:
   * full at >=210x200 (head + role + logos), medium at >=175x170 (head +
   * logos, role hidden — the collapsed tile keeps the owner's logo-only
   * packages), mini below (head only: name + version ≈ 82px, always inside
   * the 84px rest minimum). Height-only tiers clipped wrapped prose in
   * narrow tiles (a two-line head plus a three-line role needs ~165px, once
   * measured as a 35px overflow), so both axes gate. Applied via data-tier
   * (no react state — pure presentation, no render loops); the effect re-runs
   * on focus change (detail mounts/unmounts) and observes resizes for
   * treemap regrowth.
   */
  const tierRef = useRef<Record<string, number>>({});
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const applyTiers = () => {
      track.querySelectorAll<HTMLElement>(".dg-cell").forEach((cell) => {
        const id = cell.dataset.mod ?? "";
        const h = cell.clientHeight;
        const w = cell.clientWidth;
        const t = tierRef.current[id] ?? 0;
        let next: number;
        if (h >= 210 && w >= 200) next = 0;
        else if (t === 0 && h >= 202 && w >= 192) next = 0;
        else if (h >= 175 && w >= 170) next = 1;
        else if (t === 1 && h >= 167 && w >= 162) next = 1;
        else next = 2;
        tierRef.current[id] = next;
        cell.dataset.tier = next === 0 ? "full" : next === 1 ? "medium" : "mini";
      });
    };
    const ro = new ResizeObserver(() => applyTiers());
    track.querySelectorAll(".dg-cell").forEach((c) => ro.observe(c));
    applyTiers();
    return () => ro.disconnect();
  }, [focus]);
  /**
   * A tile's inside: the focus overlay plus the body. Shared by both faces —
   * the stacked face wraps it in a plain flow tile, the mosaic face in a
   * packed tile — so the two faces cannot drift apart. The body carries
   * `rev` (the current focus step) as its key, so it re-mounts and
   * crossfades on every reflow while rects morph — mid-flight widths never
   * catch text half-fitting. The overlay and the tile box itself are stable,
   * so keyboard focus and tier observation survive the swap.
   */
  const tileContent = (index: number, on: boolean, rev: number) => {
    const m = ordered[index];
    const version = moduleVersion(m.id);
    const dockerCmd = m.dockerCmd;
    const copied = copiedId === m.id;
    return (
      <>
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
          onClick={() => (stepper ? setStackActive(index) : focusModule(trackRef.current, index))}
        />
        <div className="dg-cell-body" key={rev}>
          <span className="dg-mosaic-head">
            <span className="dg-mosaic-name">
              <span className="text-ink-mute">digi</span>
              {m.id.replace(/^digi/, "")}
            </span>
            {/* The declared version, top-right. Roadmap modules
                declare none, so they read "roadmap" rather than a
                fabricated 0.0.0 — same honesty rule as the facts. */}
            <span className="dg-loc dg-mosaic-version">
              {version === null ? "roadmap" : `v${version}`}
            </span>
          </span>

          {/* One line of prose, in both states. The tile used to
              carry three (the short summary, a headline tagline and
              a lead paragraph) plus a three-row figures block —
              "there's just too many sections", the owner said. So
              the role is the resting line, the description appears
              only in focus, and the numbers are one line. */}
          <span className="dg-mosaic-role">{m.role}</span>

          {on ? (
            <span className="dg-mosaic-detail">
              <span className="dg-mosaic-facts">{factsLine(m)}</span>
              {/* The deeper description: the module's lead
                  paragraph. The copy is the one part allowed to
                  shrink and is clamped by CSS, while the stack row
                  and the foot below are pinned — the controls can
                  never be the thing that clips. The rest of the
                  summary is on the module's docs page and in the
                  ask answer. */}
              {m.summary[0] ? <span className="dg-mosaic-serves">{m.summary[0]}</span> : null}
            </span>
          ) : null}

          {/* The packages. Collapsed tiles show only the logos —
              the owner: "when the module cards are colapse we
              should just show the logo of the packages not the
              full name in order to save on space." The focused
              tile gets the named chips. */}
          <span className="dg-mosaic-stack">
            <StackRow items={m.stack} className={on ? "stack-row" : "stack-row compact"} />
          </span>

          {on ? (
            <span className="dg-mosaic-foot">
              {/* The compose command, click-to-copy. */}
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
              {/* The one control that may navigate. */}
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
          ) : null}
        </div>
      </>
    );
  };
  /* The mosaic box, measured: the treemap solves in pixels against the real
     box, so the tiles fill it exactly at every viewport size. */
  const mosaicRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = mosaicRef.current;
    if (!el) return;
    const apply = () => setBox({ w: el.clientWidth, h: el.clientHeight });
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, [stepper]);
  const weights = BASE_WEIGHTS.map((w, i) =>
    i === focus ? Math.max(w * FOCUS_MULT, FOCUS_FLOOR) : w,
  );
  /**
   * Measured top-up per module id: the solver sizes the focused tile from
   * `FOCUS_MIN`, but detail height depends on wrapping (lead length, chip
   * count, docker presence) at the solved width, which no static number can
   * predict. One settle-tick after each focus lands, the effect below
   * measures the focused body's true shortfall and records it here; that
   * module's minimum becomes the measured need plus slack. Monotonic (only
   * ever grows) and generous in one jump, so it lands in a single round —
   * and a wider re-solve can only shrink the true need, never reopen a clip.
   */
  const [needExtra, setNeedExtra] = useState<Record<string, number>>({});
  useEffect(() => {
    if (stepper) return;
    let timer: number | null = null;
    const measure = () => {
      timer = null;
      const tile = trackRef.current?.querySelector<HTMLElement>(".dg-cell.on");
      const body = tile?.querySelector<HTMLElement>(".dg-cell-body");
      if (!tile || !body) return;
      const shortfall = body.scrollHeight - body.clientHeight;
      if (shortfall > 4) {
        const id = tile.dataset.mod ?? "";
        setNeedExtra((prev) => {
          const want = Math.ceil(tile.clientHeight + shortfall + 32);
          return want > (prev[id] ?? 0) ? { ...prev, [id]: want } : prev;
        });
      }
    };
    /* Past the rect morph (0.45s) and the body fade (0.28s): measuring
       mid-flight would record a transient width's need and over-provision. */
    timer = window.setTimeout(measure, 650);
    return () => {
      if (timer !== null) window.clearTimeout(timer);
    };
    /* `needExtra` is a dep so a correction that still falls short schedules
       its own settled re-measure and heals itself; the record only ever grows
       while a real shortfall exists, so the loop always terminates. */
  }, [focus, stepper, box, needExtra]);
  const mins = BASE_WEIGHTS.map((_, i) => {
    if (i === focus) {
      const extra = needExtra[ordered[i].id] ?? 0;
      return {
        minW: FOCUS_MIN.minW + TREEMAP_GAP,
        minH: Math.max(FOCUS_MIN.minH, extra) + TREEMAP_GAP,
      };
    }
    return { minW: REST_MIN.minW + TREEMAP_GAP, minH: REST_MIN.minH + TREEMAP_GAP };
  });
  /* v18: the rest layout is the stable map — solved once with unfocused
     weights, so every tile's resting spot never moves between foci. The
     focused tile keeps its rest top-left and grows there; the rest reflow
     around it (see `treemapAnchored`). */
  const restMins = BASE_WEIGHTS.map(() => ({
    minW: REST_MIN.minW + TREEMAP_GAP,
    minH: REST_MIN.minH + TREEMAP_GAP,
  }));
  const restRects =
    !stepper && box.w > 0 && box.h > 0
      ? treemapAreasConstrained(BASE_WEIGHTS, box.w, box.h, restMins)
      : null;
  const rects =
    !stepper && box.w > 0 && box.h > 0
      ? (() => {
          if (focus < 0 || !restRects) return restRects;
          const grown = treemapAreasConstrained(weights, box.w, box.h, mins);
          const size = grown[focus];
          if (!size) return restRects;
          return treemapAnchored(weights, box.w, box.h, mins, restRects, focus, {
            w: size.w,
            h: size.h,
          });
        })()
      : null;

  return (
    <section id="architecture" className="line-t line-b">
      {/* Standard section delimiters above and below the grid (owner: the
          same line-t/line-b grammar every other section uses). The stub
          dotted verticals are gone — that space stays empty by direction. */}
      <div
        ref={trackRef}
        style={
          stepper
            ? undefined
            : { height: `${scrollyTrackHeightVh(ordered.length, VH_PER_MODULE)}vh` }
        }
      >
        <div className={stepper ? "dg-stack-wrap" : "dg-stage dg-stage--mosaic"}>
          <div
            ref={mosaicRef}
            className={`dg-mosaic ${stepper ? "dg-mosaic--stack" : "dg-mosaic--rows"}`}
            role="list"
            aria-label="digithings modules, sized by lines of code"
          >
            {stepper ? (
              STACK_ROWS.map((members, row) => (
                <div key={`row-${row}`} className="dg-mosaic-row">
                  {members.map((i) => {
                    const on = reduced || i === stackActive;
                    /* Slide-up entrance per card: the kit's Reveal (fade + rise
                       from below, once, whileInView) — the digiweb card deck's
                       own entrance vocabulary. The focal ref stays on the tile
                       itself, which shares the wrapper's top. */
                    return (
                      <Reveal
                        key={ordered[i].id}
                        className="dg-stack-reveal"
                        delay={Math.min(i * 0.05, 0.3)}
                      >
                        <div
                          data-mod={ordered[i].id}
                          ref={(el) => {
                            stackRefs.current[i] = el;
                          }}
                          role="listitem"
                          className={`dg-cell${on ? " on" : ""}`}
                          aria-current={on ? "true" : undefined}
                        >
                          {tileContent(i, on, -1)}
                        </div>
                      </Reveal>
                    );
                  })}
                </div>
              ))
            ) : (
              ordered.map((m, i) => {
                const r = rects?.[i];
                const on = i === focus;
                return (
                  <div
                    key={m.id}
                    data-mod={m.id}
                    role="listitem"
                    className={`dg-cell${on ? " on" : ""}`}
                    aria-current={on ? "true" : undefined}
                    /* Hidden until the first solve lands: the box is measured
                       one effect-tick after mount, and unpositioned tiles must
                       not flash piled at the corner. `visibility` (not
                       opacity) so the CSS rest/focus/hover opacities stay
                       the owners of fading. Geometry rides the CSS rect
                       transition in web-theme on the brand curve — the kit's
                       motion vocabulary is transform/opacity only, so rect
                       interpolation lives in CSS, driven by motion's
                       `useScroll` walk upstream. */
                    style={
                      r
                        ? ({
                            visibility: "visible",
                            left: r.x + TREEMAP_GAP / 2,
                            top: r.y + TREEMAP_GAP / 2,
                            width: Math.max(r.w - TREEMAP_GAP, 0),
                            height: Math.max(r.h - TREEMAP_GAP, 0),
                          } as React.CSSProperties)
                        : ({ visibility: "hidden" } as React.CSSProperties)
                    }
                  >
                    {tileContent(i, on, focus)}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
