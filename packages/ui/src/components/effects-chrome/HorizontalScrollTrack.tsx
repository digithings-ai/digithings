"use client";

import {
  Children,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useMotionValue, useMotionValueEvent, useScroll, useTransform, type MotionValue } from "motion/react";
import { m, useMotionSafe } from "../../motion/primitives";
import { cn } from "../../lib/utils";
import {
  TRACK_MIN_WIDTH,
  clamp,
  focusTargetX,
  nearestIndex,
  runwayHeight,
  scrollTopForX,
  trackTravel,
} from "./horizontal-track-core";

/**
 * HorizontalScrollTrack — a row of cards that a vertical scroll drives sideways.
 *
 * Wide + motion allowed (>= `minWidth`, default 960px): a `position: sticky`
 * pin holds the row while the page scrolls; the runway's height is DERIVED from
 * the track's content width (pin height + horizontal travel, re-measured by
 * ResizeObserver), so 1px of scroll is 1px of travel and the next section can
 * never overlap the pin. The translate is a motion-value function transform of
 * scroll progress — written straight to the element, no per-frame setState.
 *
 * Narrow, reduced-motion, first paint, and no-JS: a native scroll-snap strip
 * with every card reachable (the honest fallback, never a hidden state).
 *
 * Accessibility: each child is wrapped in a `role="listitem"` tab stop in DOM
 * order. Focusing an off-screen card scrolls the runway to it (pinned) or lets
 * the browser scroll the strip (native). The pinned viewport is `overflow-x:
 * clip`, never a scroll container, so focus cannot skew the transform.
 *
 * Progress is exposed two ways: `header` / `footer` may be render props that
 * receive the state, and `useHorizontalTrack()` reads it from context (used by
 * `HorizontalTrackStepper`). `progress` is a MotionValue (0..1) so a consumer
 * animates from it with transforms and never re-renders per frame; `activeIndex`
 * is React state that only changes when the leading card changes.
 *
 * One pin per page (plan section 2). Wiring (in the consuming app):
 *   globals.css   @source "<path-to>/packages/ui/src/components/effects-chrome";
 * No CSS sheet — everything is utilities. Requires MotionProvider (`m.*`).
 */
export type HorizontalTrackState = {
  /** Scroll progress through the track, 0..1 (a MotionValue, not React state). */
  progress: MotionValue<number>;
  /** Index of the card at the leading edge; changes only at card boundaries. */
  activeIndex: number;
  /** Number of cards. */
  count: number;
  /** True while the sticky pin is active; false for the native snap strip. */
  pinned: boolean;
  /** Bring card `index` to the leading edge (scrolls the runway or the strip). */
  goTo: (index: number) => void;
};

export type HorizontalScrollTrackProps = {
  /** The cards. Each direct child becomes one tab-stop track item. */
  children: ReactNode;
  /** Accessible name for the list of cards. */
  ariaLabel: string;
  /** Content above the row (inside the pin). Node or render prop. */
  header?: ReactNode | ((state: HorizontalTrackState) => ReactNode);
  /** Content below the row (inside the pin) — e.g. a HorizontalTrackStepper. */
  footer?: ReactNode | ((state: HorizontalTrackState) => ReactNode);
  /** Classes on each track item wrapper (sets the card width). */
  itemClassName?: string;
  /** Classes on the outermost element. */
  className?: string;
  /** Sticky offset in px — set to the height of chrome pinned above (nav). */
  pinTop?: number;
  /** Pin only at this viewport width and up. Default 960. */
  minWidth?: number;
};

const TrackContext = createContext<HorizontalTrackState | null>(null);

/** Read the track's progress state from a descendant (header / footer / card). */
export function useHorizontalTrack(): HorizontalTrackState {
  const state = useContext(TrackContext);
  if (!state) throw new Error("useHorizontalTrack must be used inside <HorizontalScrollTrack>");
  return state;
}

const useIsoLayoutEffect = typeof document !== "undefined" ? useLayoutEffect : useEffect;

function useMinWidth(px: number): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(`(min-width: ${px}px)`);
    const apply = () => setMatches(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [px]);
  return matches;
}

/** Leading-edge offset of each item, relative to the first (padding-agnostic). */
function readOffsets(track: HTMLElement): number[] {
  const kids = Array.from(track.children).filter((c): c is HTMLElement => c instanceof HTMLElement);
  const base = kids[0]?.offsetLeft ?? 0;
  return kids.map((k) => k.offsetLeft - base);
}

function slot(
  node: HorizontalTrackProps["header"],
  state: HorizontalTrackState,
): ReactNode {
  return typeof node === "function" ? node(state) : node;
}
type HorizontalTrackProps = HorizontalScrollTrackProps;

// Edge fade for the row: alpha stops through a token (mask uses alpha only), so
// no raw colour. 1.5rem matches the track's inline padding so the first card at
// rest is fully opaque.
const FADE =
  "[mask-image:linear-gradient(90deg,transparent,var(--ink)_1.5rem,var(--ink)_calc(100%_-_1.5rem),transparent)]";

const ITEM_FOCUS =
  "focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent";
const ITEM_DEFAULT_WIDTH = "w-[min(82vw,22rem)]";

type BodyProps = {
  items: ReactNode[];
  ariaLabel: string;
  header: HorizontalTrackProps["header"];
  footer: HorizontalTrackProps["footer"];
  itemClassName?: string;
  className?: string;
  progress: MotionValue<number>;
  state: HorizontalTrackState;
  setActive: (i: number) => void;
  goToRef: RefObject<(i: number) => void>;
};

function Items({
  items,
  itemClassName,
  onItemFocus,
}: {
  items: ReactNode[];
  itemClassName?: string;
  onItemFocus?: (el: HTMLElement) => void;
}) {
  return items.map((child, i) => (
    <div
      key={i}
      role="listitem"
      tabIndex={0}
      data-track-item=""
      className={cn("flex-none snap-start", ITEM_DEFAULT_WIDTH, ITEM_FOCUS, itemClassName)}
      onFocus={(e) => onItemFocus?.(e.currentTarget)}
    >
      {child}
    </div>
  ));
}

/** Native scroll-snap strip: the default, the narrow, and the reduced-motion render. */
function StripBody({
  items,
  ariaLabel,
  header,
  footer,
  itemClassName,
  className,
  progress,
  state,
  setActive,
  goToRef,
}: BodyProps) {
  const stripRef = useRef<HTMLDivElement | null>(null);
  const safe = useMotionSafe();
  const lastIndex = useRef(0);

  const onScroll = useCallback(() => {
    const el = stripRef.current;
    if (!el) return;
    const range = el.scrollWidth - el.clientWidth;
    progress.set(range > 0 ? clamp(el.scrollLeft / range, 0, 1) : 0);
    const idx = nearestIndex(readOffsets(el), el.scrollLeft);
    if (idx !== lastIndex.current) {
      lastIndex.current = idx;
      setActive(idx);
    }
  }, [progress, setActive]);

  useEffect(() => {
    goToRef.current = (index) => {
      const el = stripRef.current;
      if (!el) return;
      const offsets = readOffsets(el);
      const left = offsets[clamp(index, 0, offsets.length - 1)] ?? 0;
      el.scrollTo({ left, behavior: safe ? "smooth" : "auto" });
    };
    progress.set(0);
    // A strip mounts at scrollLeft 0; drop any index carried over from the pinned body.
    lastIndex.current = 0;
    setActive(0);
  }, [goToRef, progress, safe, setActive]);

  return (
    <div className={cn("relative", className)} data-track="strip">
      {slot(header, state)}
      <div className={FADE}>
        <div
          ref={stripRef}
          role="list"
          aria-label={ariaLabel}
          onScroll={onScroll}
          className="relative flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-ps-6 px-6 pb-3 [scrollbar-width:thin]"
        >
          <Items items={items} itemClassName={itemClassName} />
        </div>
      </div>
      {slot(footer, state)}
    </div>
  );
}

/** Sticky pin: runway height from content width, translate from scroll progress. */
function PinnedBody({
  items,
  ariaLabel,
  header,
  footer,
  itemClassName,
  className,
  progress,
  state,
  setActive,
  goToRef,
  pinTop,
}: BodyProps & { pinTop: number }) {
  const runwayRef = useRef<HTMLDivElement | null>(null);
  const pinRef = useRef<HTMLDivElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const offsets = useRef<number[]>([]);
  const lastIndex = useRef(0);
  const travel = useMotionValue(0);
  const [runwayPx, setRunwayPx] = useState<number | undefined>(undefined);

  const { scrollYProgress } = useScroll({
    target: runwayRef,
    offset: [`start ${pinTop}px` as `start ${number}px`, "end end"],
  });
  // Function transform: scroll progress and measured travel in, translateX out.
  const x = useTransform([scrollYProgress, travel], ([p, t]: number[]) => -clamp(p, 0, 1) * t);

  useMotionValueEvent(scrollYProgress, "change", (p) => {
    progress.set(p);
    const idx = nearestIndex(offsets.current, clamp(p, 0, 1) * travel.get());
    if (idx !== lastIndex.current) {
      lastIndex.current = idx;
      setActive(idx);
    }
  });

  const measure = useCallback(() => {
    const track = trackRef.current;
    const viewport = viewportRef.current;
    const pin = pinRef.current;
    if (!track || !viewport || !pin) return;
    const t = trackTravel(track.scrollWidth, viewport.clientWidth);
    offsets.current = readOffsets(track);
    travel.set(t);
    setRunwayPx(runwayHeight(pin.clientHeight, t));
  }, [travel]);

  useIsoLayoutEffect(() => {
    measure();
    progress.set(scrollYProgress.get());
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    for (const el of [trackRef.current, viewportRef.current, pinRef.current]) {
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [measure, progress, scrollYProgress]);

  const scrollToX = useCallback(
    (target: number, behavior: ScrollBehavior) => {
      const runway = runwayRef.current;
      if (!runway) return;
      window.scrollTo({
        top: scrollTopForX({
          runwayTopInDocument: runway.getBoundingClientRect().top + window.scrollY,
          pinTop,
          x: target,
          travel: travel.get(),
        }),
        behavior,
      });
    },
    [pinTop, travel],
  );

  useEffect(() => {
    goToRef.current = (index) => {
      const list = offsets.current;
      if (list.length === 0) return;
      scrollToX(list[clamp(index, 0, list.length - 1)] ?? 0, "smooth");
    };
  }, [goToRef, scrollToX]);

  /** Focus moved to a card: reveal it by scrolling the runway (instant, so the
   *  focus ring never chases a smooth scroll). */
  const onItemFocus = useCallback(
    (el: HTMLElement) => {
      const viewport = viewportRef.current;
      const track = trackRef.current;
      if (!viewport || !track) return;
      const base = (track.children[0] as HTMLElement | undefined)?.offsetLeft ?? 0;
      const target = focusTargetX({
        itemLeft: el.offsetLeft - base,
        itemWidth: el.offsetWidth,
        currentX: -x.get(),
        viewportWidth: viewport.clientWidth - 2 * base,
        travel: travel.get(),
      });
      if (target !== null) scrollToX(target, "auto");
    },
    [scrollToX, travel, x],
  );

  return (
    <div
      ref={runwayRef}
      className={cn("relative", className)}
      style={{ height: runwayPx }}
      data-track="pinned"
    >
      <div
        ref={pinRef}
        className="sticky flex flex-col justify-center gap-6 overflow-x-clip"
        style={{ top: pinTop, height: `calc(100svh - ${pinTop}px)` }}
      >
        {slot(header, state)}
        <div ref={viewportRef} className={cn("overflow-x-clip", FADE)}>
          <m.div
            ref={trackRef}
            role="list"
            aria-label={ariaLabel}
            style={{ x }}
            className="relative flex w-max gap-4 px-6 will-change-transform"
          >
            <Items items={items} itemClassName={itemClassName} onItemFocus={onItemFocus} />
          </m.div>
        </div>
        {slot(footer, state)}
      </div>
    </div>
  );
}

export function HorizontalScrollTrack({
  children,
  ariaLabel,
  header,
  footer,
  itemClassName,
  className,
  pinTop = 0,
  minWidth = TRACK_MIN_WIDTH,
}: HorizontalScrollTrackProps) {
  const items = Children.toArray(children);
  const safe = useMotionSafe();
  const wide = useMinWidth(minWidth);
  const pinned = safe && wide;
  const progress = useMotionValue(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const goToRef = useRef<(index: number) => void>(() => {});
  const goTo = useCallback((index: number) => goToRef.current(index), []);
  const count = items.length;

  const state = useMemo<HorizontalTrackState>(
    () => ({ progress, activeIndex, count, pinned, goTo }),
    [progress, activeIndex, count, pinned, goTo],
  );

  const body: BodyProps = {
    items,
    ariaLabel,
    header,
    footer,
    itemClassName,
    className,
    progress,
    state,
    setActive: setActiveIndex,
    goToRef,
  };

  return (
    <TrackContext.Provider value={state}>
      {pinned ? <PinnedBody {...body} pinTop={pinTop} /> : <StripBody {...body} />}
    </TrackContext.Provider>
  );
}

/**
 * HorizontalTrackStepper — the stage stepper for a track: a hairline rail whose
 * fill scales with progress (transform only) over one button per card that
 * highlights the active card and jumps to it. Reads the track from context, so
 * it belongs in the track's `header` / `footer`. Labels are plain text, so the
 * stepper reads with no JS (the buttons simply do nothing then).
 */
export function HorizontalTrackStepper({
  labels,
  className,
}: {
  /** One label per card, in card order. */
  labels: string[];
  className?: string;
}) {
  const { progress, activeIndex, goTo } = useHorizontalTrack();
  return (
    <div className={cn("grid gap-3 px-6", className)}>
      <div className="h-px bg-hair" aria-hidden="true">
        <m.div
          className="h-px origin-left bg-accent rtl:origin-right"
          style={{ scaleX: progress }}
        />
      </div>
      <ol className="m-0 flex list-none flex-wrap gap-x-5 gap-y-2 p-0 font-mono text-[0.68rem] tracking-[0.04em]">
        {labels.map((label, i) => (
          <li key={label}>
            <button
              type="button"
              onClick={() => goTo(i)}
              aria-current={i === activeIndex ? "step" : undefined}
              className={cn(
                "cursor-pointer bg-transparent p-0 font-[inherit] transition-colors hover:text-ink focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent motion-reduce:transition-none",
                i === activeIndex ? "text-ink" : "text-ink-mute",
              )}
            >
              <span aria-hidden="true">{i === activeIndex ? "▸" : String(i + 1).padStart(2, "0")}</span>{" "}
              {label}
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
