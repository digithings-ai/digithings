"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import type { ModuleNode } from "../../data/modules";
import { Reveal } from "../../motion/primitives";
import { useScrollyFeatures } from "../../motion/scrolly";
import { scrollyTrackHeightVh } from "../../motion/scrolly-core";
import { StackRow } from "../StackLogo";
import { treemapAnchored, treemapAreasConstrained, type TreemapMins } from "./treemap";

/**
 * The module mosaic: one angular tile per module, each tile's area its share
 * of the stack's lines of code, and a focus that walks the tiles as the page
 * scrolls. Promoted from digithings-web's landing (#4429).
 *
 * - **Order is size.** Biggest module top-left, smallest last; roadmap modules
 *   (no lines) sink to the end. `graphOrder` breaks ties. The reading order is
 *   the scroll order, so the focus walks biggest to smallest.
 * - **Packing.** A squarified treemap (`treemapAreasConstrained`) solved in
 *   pixels against the measured box. The rest layout is solved once and never
 *   moves; the focused tile keeps its rest top-left and grows there while the
 *   others repack around it (`treemapAnchored`). Rects ease on the CSS
 *   left/top/width/height transition in `web-theme.css` (`.dg-cell`).
 * - **Focus.** `useScrollyFeatures` maps the pinned track's progress to a
 *   tile. Focus only engages while the stage is centred in the viewport, and
 *   clicking a tile jumps the scroll to its step (instant, so exactly one tile
 *   animates). The focused tile shows its facts, lead, packages, the compose
 *   command (click to copy) and, with `onAsk`, an "ask digichat" control.
 * - **Small screens / reduced motion.** `useScrollyFeatures` flips to
 *   `stepper`: the same tiles stack one per row, all open, and the one at the
 *   focal line lights (all of them under reduced motion) — paint only, so the column
 *   never changes height under the reader.
 * - **Density tiers.** Each tile's measured size sets `data-tier`
 *   (full / medium / mini) with hysteresis, so a tile shows what fits and the
 *   name and version never clip.
 */
export interface ModuleGridItem {
  module: ModuleNode;
  /** Lines of code. `null` marks a roadmap module: half the floor weight, sorted last. */
  lines: number | null;
  /** Declared version, or `null` (renders "roadmap" rather than a fabricated 0.0.0). */
  version: string | null;
  /** Extra facts after the line count, e.g. "12 endpoints · 9 MCP tools". */
  counts?: string;
}

export interface ModuleGridProps {
  items: ModuleGridItem[];
  /** Shows the focused tile's "ask digichat" control and handles it. */
  onAsk?: (id: string) => void;
  /** Accessible name of the tile list. */
  label?: string;
  /** Scroll length per module on the pinned track, in vh. */
  vhPerModule?: number;
  className?: string;
}

/** The exponent on the normalised log weight. >1 spreads the field. */
const WEIGHT = 1.5;
/** The share of the biggest module the smallest shipped module still draws, before weighting. */
const WEIGHT_FLOOR = 0.12;
/**
 * Roadmap modules draw half the floor: a module with no code is not a module
 * with no size, but it is honestly smaller than the smallest shipped one.
 * Full-floor roadmaps would draw the same rect as the smallest shipped module.
 */
const ROADMAP_WEIGHT = WEIGHT_FLOOR * 0.5;
/**
 * How the focused module's weight is lifted while the layout is solved: the
 * multiplier keeps big tiles modest, the floor guarantees small tiles room
 * for their detail. Unfocused tiles keep their exact weight ratios.
 */
const FOCUS_MULT = 1.3;
const FOCUS_FLOOR = 0.5;
/** Rest tiles fit name + version; focused tiles fit their detail (refined per module by `needExtra`). */
const REST_MIN: TreemapMins = { minW: 150, minH: 84 };
const FOCUS_MIN: TreemapMins = { minW: 300, minH: 260 };
/** The gutter between packed tiles, in px — each rect is inset by half. */
const TREEMAP_GAP = 8;
/** The stacked face's focal line, as a share of the viewport height. */
const STACK_FOCAL = 0.38;
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/** Hydration-safe reduced-motion read: `false` on the server and first client render. */
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

/** Biggest first; roadmap modules last, ordered among themselves by `graphOrder`. */
function sortBySize(items: ModuleGridItem[]): ModuleGridItem[] {
  return [...items].sort((a, b) => {
    if (a.lines === null && b.lines === null) return a.module.graphOrder - b.module.graphOrder;
    if (a.lines === null) return 1;
    if (b.lines === null) return -1;
    return b.lines - a.lines;
  });
}

/**
 * Size weights on a log axis, so a 188x line-count spread still leaves the
 * smallest tile legible. The floor is applied before the exponent so no
 * shipped module can reach zero.
 */
function sizeWeights(ordered: ModuleGridItem[]): number[] {
  const measured = ordered.map((item) => item.lines).filter((n): n is number => n !== null && n > 0);
  if (measured.length === 0) return ordered.map(() => 1);
  const logMin = Math.min(...measured.map((n) => Math.log10(n)));
  const logMax = Math.log10(Math.max(...measured));
  const span = Math.max(logMax - logMin, 1);
  return ordered.map((item) => {
    if (item.lines === null || item.lines <= 0) return ROADMAP_WEIGHT;
    const t = (Math.log10(item.lines) - logMin) / span;
    return WEIGHT_FLOOR + (1 - WEIGHT_FLOOR) * Math.pow(t, WEIGHT);
  });
}

function factsLine(item: ModuleGridItem): string {
  const size = item.lines === null ? "roadmap" : `${item.lines.toLocaleString("en-US")} lines`;
  return [size, item.counts].filter(Boolean).join(" · ");
}

/**
 * Move the page so `index` is the step the pin shows: the centre of step
 * `index` sits at `(index + 0.5) / count` of the track's scroll span. Instant,
 * not smooth — a smooth scroll would walk the focus through every tile between.
 */
function focusModule(track: HTMLElement | null, index: number, count: number) {
  if (!track) return;
  const top = track.getBoundingClientRect().top + window.scrollY;
  const span = Math.max(track.offsetHeight - window.innerHeight, 1);
  const target = top + ((index + 0.5) / count) * span;
  window.scrollTo({ top: Math.max(target, 0), behavior: "auto" });
}

/**
 * Copy text via the Clipboard API, falling back to a hidden textarea. Resolves
 * to whether the copy happened, so a refused copy never claims success.
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

export function ModuleGrid({
  items,
  onAsk,
  label = "digithings modules, sized by lines of code",
  vhPerModule = 48,
  className,
}: ModuleGridProps) {
  const ordered = useMemo(() => sortBySize(items), [items]);
  const baseWeights = useMemo(() => sizeWeights(ordered), [ordered]);
  const count = ordered.length;

  const trackRef = useRef<HTMLDivElement>(null);
  const { activeIndex, stepper } = useScrollyFeatures(trackRef, { slideCount: count });
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const copyTimer = useRef<number | null>(null);
  const reduced = usePrefersReducedMotion();

  /* The stacked face opens the tile nearest the focal line; the first tile
     reads open at page top. */
  const stackRefs = useRef<Array<HTMLElement | null>>([]);
  const [stackActive, setStackActive] = useState(0);

  /* Focus engages only while the stage is centred (middle third, with a wider
     release skirt against flapping) and a little way into the walk. Gate on the
     stage box: the mosaic's own box is what grows, so gating on it deadlocks. */
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
      const stage = track.querySelector(".dg-stage--mosaic");
      const rect = (stage ?? mosaic).getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const center = rect.top + rect.height / 2;
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

  /* Density tiers from measured width and height, with an 8px hysteresis skirt
     per dimension. Written to data-tier directly: pure presentation, no state. */
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

  /* A tile's inside, shared by both faces. The body is keyed by `rev` so it
     re-mounts and crossfades when its content changes — only the tile gaining
     focus and the one losing it; resting tiles keep their key and just glide,
     so a step never blanks the whole grid. The focus overlay sits under the
     body (a button cannot contain the tile's own controls). */
  const tileContent = (index: number, on: boolean, rev: number) => {
    const item = ordered[index];
    const m = item.module;
    const dockerCmd = m.dockerCmd;
    const copied = copiedId === m.id;
    return (
      <>
        <button
          type="button"
          className="dg-cell-focus"
          aria-label={`Focus ${m.id} — ${m.role}, ${factsLine(item)}`}
          onClick={() =>
            stepper ? setStackActive(index) : focusModule(trackRef.current, index, count)
          }
        />
        <div className="dg-cell-body" key={rev}>
          <span className="dg-mosaic-head">
            <span className="dg-mosaic-name">
              <span className="text-ink-mute">digi</span>
              {m.id.replace(/^digi/, "")}
            </span>
            <span className="dg-loc dg-mosaic-version">
              {item.version === null ? "roadmap" : `v${item.version}`}
            </span>
          </span>

          <span className="dg-mosaic-role">{m.role}</span>

          {on ? (
            <span className="dg-mosaic-detail">
              <span className="dg-mosaic-facts">{factsLine(item)}</span>
              {m.summary[0] ? <span className="dg-mosaic-serves">{m.summary[0]}</span> : null}
            </span>
          ) : null}

          <span className="dg-mosaic-stack">
            <StackRow items={m.stack} className={on ? "stack-row" : "stack-row compact"} />
          </span>

          {on ? (
            <span className="dg-mosaic-foot">
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
              {onAsk ? (
                <button
                  type="button"
                  className="dg-mosaic-ask"
                  aria-label={`Ask digichat about ${m.id}`}
                  onClick={() => onAsk(m.id)}
                >
                  ask <span className="text-ink">digi</span>
                  <span className="text-accent">chat</span> →
                </button>
              ) : null}
            </span>
          ) : null}
        </div>
      </>
    );
  };

  /* The treemap solves in pixels against the measured box. */
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

  /* A new box re-solves every rect. That is layout, not motion: tiles jump to
     it rather than easing (only a focus change glides), and the mosaic stays
     unseen until the box has held still once after the first solve, then fades
     in whole — so a load never shows tiles piled in a corner or growing into
     place. Attributes, not state: they must land in the same frame as the
     rects, before paint. */
  useLayoutEffect(() => {
    const el = mosaicRef.current;
    if (!el || stepper || box.w === 0 || box.h === 0) return;
    el.setAttribute("data-resizing", "");
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => el.removeAttribute("data-resizing"));
    });
    const settle = window.setTimeout(() => el.setAttribute("data-settled", ""), 160);
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
      window.clearTimeout(settle);
    };
  }, [box.w, box.h, stepper]);

  const weights = baseWeights.map((w, i) => (i === focus ? Math.max(w * FOCUS_MULT, FOCUS_FLOOR) : w));

  /* Measured top-up per module: one settle-tick after focus lands, the focused
     body's true shortfall raises that module's minimum. Monotonic, so the
     re-measure loop always terminates. */
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
    /* Past the rect morph (0.45s) and the body fade (0.28s). */
    timer = window.setTimeout(measure, 650);
    return () => {
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [focus, stepper, box, needExtra]);

  const mins = baseWeights.map((_, i) => {
    if (i === focus) {
      const extra = needExtra[ordered[i].module.id] ?? 0;
      return {
        minW: FOCUS_MIN.minW + TREEMAP_GAP,
        minH: Math.max(FOCUS_MIN.minH, extra) + TREEMAP_GAP,
      };
    }
    return { minW: REST_MIN.minW + TREEMAP_GAP, minH: REST_MIN.minH + TREEMAP_GAP };
  });
  const restMins = baseWeights.map(() => ({
    minW: REST_MIN.minW + TREEMAP_GAP,
    minH: REST_MIN.minH + TREEMAP_GAP,
  }));
  const solvable = !stepper && box.w > 0 && box.h > 0;
  const restRects = solvable ? treemapAreasConstrained(baseWeights, box.w, box.h, restMins) : null;
  let rects = restRects;
  if (solvable && focus >= 0 && restRects) {
    const size = treemapAreasConstrained(weights, box.w, box.h, mins)[focus];
    if (size) {
      rects = treemapAnchored(weights, box.w, box.h, mins, restRects, focus, { w: size.w, h: size.h });
    }
  }

  return (
    <div
      ref={trackRef}
      className={className}
      style={stepper ? undefined : { height: `${scrollyTrackHeightVh(count, vhPerModule)}vh` }}
    >
      <div className={stepper ? "dg-stack-wrap" : "dg-stage dg-stage--mosaic"}>
        <div
          ref={mosaicRef}
          className={`dg-mosaic ${stepper ? "dg-mosaic--stack" : "dg-mosaic--rows"}`}
          role="list"
          aria-label={label}
        >
          {stepper
            ? ordered.map((item, i) => {
                const on = reduced || i === stackActive;
                return (
                  <div key={item.module.id} className="dg-mosaic-row">
                    <Reveal className="dg-stack-reveal" delay={Math.min(i * 0.05, 0.3)}>
                      <div
                        data-mod={item.module.id}
                        ref={(el) => {
                          stackRefs.current[i] = el;
                        }}
                        role="listitem"
                        className={`dg-cell${on ? " on" : ""}`}
                        aria-current={on ? "true" : undefined}
                      >
                        {tileContent(i, true, -1)}
                      </div>
                    </Reveal>
                  </div>
                );
              })
            : ordered.map((item, i) => {
                const r = rects?.[i];
                const on = i === focus;
                /* Hidden until the first solve lands, so unpositioned tiles
                   never flash piled at the corner. Placed by a physical
                   translate on purpose: these are the treemap's x/y in the
                   measured box, and a transform moves a tile without
                   registering as a layout shift. */
                const style: CSSProperties = r
                  ? {
                      visibility: "visible",
                      transform: `translate(${r.x + TREEMAP_GAP / 2}px, ${r.y + TREEMAP_GAP / 2}px)`,
                      width: Math.max(r.w - TREEMAP_GAP, 0),
                      height: Math.max(r.h - TREEMAP_GAP, 0),
                    }
                  : { visibility: "hidden" };
                return (
                  <div
                    key={item.module.id}
                    data-mod={item.module.id}
                    role="listitem"
                    className={`dg-cell${on ? " on" : ""}`}
                    aria-current={on ? "true" : undefined}
                    style={style}
                  >
                    {tileContent(i, on, on ? focus : -1)}
                  </div>
                );
              })}
        </div>
      </div>
    </div>
  );
}
