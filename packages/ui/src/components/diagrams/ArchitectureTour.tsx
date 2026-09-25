"use client";
/**
 * Architecture tour — the same container diagram, walked, and then swapped.
 *
 * The owner, after seeing the first cut: "i still want to have that slide where
 * i do the guided box rings or actually the element that's selected or talked
 * about should just glow and then i still want that that swipe to the digi
 * things so we start with the diagram for the off-the-shelf solution and then we
 * swipe over to the digi things solution the guided camera while it'd be much
 * cooler just to guide the camera and make the elements glow it's currently
 * broken if you could make it work".
 *
 * So the tour takes PAIRS of sides — `[{ rented spec + steps }, { owned spec +
 * steps }]` — and runs them as ONE scroll timeline:
 *
 *   - the first side's steps hold the frame still and light its boxes (a glow,
 *     not a ring, with a spotlight that drops everything outside the box back
 *     into the page);
 *   - the last fraction of the final step runs the SWAP. Each side is ONE group
 *     — its diagram and its own step list — and the groups swap by sliding, not
 *     by fading: the rented group (diagram left, list right) leaves to the LEFT
 *     as a unit, then the owned group arrives from the RIGHT (list left and
 *     bottom-aligned, diagram right). The rail does not cross the page on its
 *     own; it travels with its diagram. The owner asked for exactly this: "the
 *     diagram slides to the left, the rented text also goes left with it. And
 *     then from the right side of the screen appears the owned text with its
 *     diagram … they don't continue one another. One replaces the other so that
 *     you should see them slide on and off the screen." So neither group is ever
 *     faded — no opacity anywhere on the swap — and the two never share the
 *     frame: the exit runs over the first half of the window and the entrance
 *     over the second;
 *   - the second side's steps then drive the camera as well as the glow.
 *
 * The camera is deliberately only on the LAST side. It can only ever zoom IN
 * (one step is the whole diagram, each later step is a subset of it), so a walk
 * can never zoom in and then have to pull back out — which is what made the
 * earlier version read as empty space and clipping.
 *
 * HOW IT KNOWS WHERE ANYTHING IS. It does not. mermaid's layout is its own, so
 * the tour measures the rendered SVG after the fact: each service is emitted as
 * `<g id="arch-…-service-<id>">` and each boundary as `<g id="arch-…-group-<id>">`,
 * which makes every box addressable by id without touching mermaid internals or
 * hard-coding coordinates. Measurements are taken once each SVG appears (a
 * MutationObserver on the stage) and again on resize, always while that pane's
 * camera is untransformed so the numbers are in unscaled pane space.
 *
 * MOTION BUDGET. One rAF-throttled passive scroll listener writing custom
 * properties (`--arch-out` / `--arch-in` on the grid; `--arch-p` on the pin);
 * React state changes only when the coarse step index changes. Reduced motion
 * gets the static treatment, and so does anything narrower than the breakpoint
 * at which the pinned layout fits.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { ArchitectureDiagram, type ArchSpec } from "./ArchitectureDiagram";

export interface TourStep {
  id: string;
  label: string;
  line: string;
  /** Box ids this step is about. Empty means "the whole diagram". */
  ids: string[];
}

export interface TourSide {
  spec: ArchSpec;
  steps: TourStep[];
  /** Short marker for the rail, e.g. "rented" / "owned". */
  tag?: string;
  caption?: string;
  /**
   * Which edge this side's step column shows its progress rule on, and with it
   * the step text alignment: "start" (default, rule left) or "end" (rule right,
   * text right-aligned to it). Per side, so the rented column can sit right
   * while the owned one keeps the left.
   */
  rail?: "start" | "end";
}

export type TourVariant = "static" | "highlight" | "camera";

export interface ArchitectureTourProps {
  /** One side is a plain walk; two add the swipe between them. */
  sides: TourSide[];
  variant?: TourVariant;
  /** Scroll spent per step, in viewport heights. */
  vhPerStep?: number;
  /**
   * Held inside the pin, above the diagram, so a title/lede stays on screen for
   * the whole walk instead of scrolling away when the walk begins.
   */
  header?: ReactNode;
  className?: string;
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface SideMeasure {
  boxes: Record<string, Box>;
  w: number;
  h: number;
}

const NO_MOTION = "(prefers-reduced-motion: reduce)";
// Must agree with the two-column grid breakpoint in diagrams.css: below it the
// rail has nowhere to travel to, so the animated treatment cannot hold.
const PIN_MEDIA = "(min-width: 1024px)";

const clamp01 = (n: number): number => Math.max(0, Math.min(1, n));
const smooth = (n: number): number => {
  const t = clamp01(n);
  return t * t * (3 - 2 * t);
};

/** Where a pinned frame parks under the sticky nav. */
function pinOffset(): number {
  const nav = Number.parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue("--dq-nav-h"),
  );
  return (Number.isFinite(nav) ? nav : 72) + 16;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(NO_MOTION);
    const sync = () => setReduced(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return reduced;
}

/** True while the viewport is wide enough for the pinned two-column layout. */
function usePinned(): boolean {
  const [pinned, setPinned] = useState(false);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(PIN_MEDIA);
    const sync = () => setPinned(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return pinned;
}

export function ArchitectureTour({
  sides,
  variant = "static",
  vhPerStep = 1.6,
  header,
  className,
}: ArchitectureTourProps) {
  const reduced = usePrefersReducedMotion();
  const wide = usePinned();
  // The animated treatments need a pin to exist; without one they read as the
  // static treatment rather than pinning to nothing.
  const mode: TourVariant = reduced || !wide ? "static" : variant;

  const trackRef = useRef<HTMLDivElement | null>(null);
  const pinRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const paneRefs = useRef<Array<HTMLDivElement | null>>([]);
  const cameraRefs = useRef<Array<HTMLDivElement | null>>([]);
  /** Set by the scroll effect so a late-arriving SVG can resize the track. */
  const remeasureRef = useRef<() => void>(() => {});

  const [measures, setMeasures] = useState<SideMeasure[]>([]);
  const [step, setStep] = useState(0);

  const flat = useMemo(
    () => sides.flatMap((side, si) => side.steps.map((entry) => ({ ...entry, side: si }))),
    [sides],
  );
  const count = flat.length;
  /** The flat index at which the swipe has finished and the last side is live. */
  const swapAt = sides.length > 1 ? sides[0].steps.length : count;

  /* ── measure each rendered diagram ─────────────────────────────────── */

  useEffect(() => {
    // The media queries resolve after mount, so the FIRST render is always the
    // static branch — there is no stage to measure yet. Depending on `mode` is
    // what re-runs this once the pinned layout exists; without it the effect
    // returned early forever and nothing was ever measured.
    if (mode === "static") return;
    const stage = stageRef.current;
    if (!stage) return;

    /** Returns true once every side has at least one measured box. */
    const measure = (): boolean => {
      let done = true;
      const next = sides.map((side, si) => {
        const empty: SideMeasure = { boxes: {}, w: 0, h: 0 };
        const pane = paneRefs.current[si];
        if (!pane) {
          done = false;
          return empty;
        }
        const svg = pane.querySelector("svg");
        if (!svg) {
          done = false;
          return empty;
        }
        const origin = svg.getBoundingClientRect();
        if (origin.width === 0) {
          done = false;
          return empty;
        }
        const ids = [
          ...side.spec.services.map((s) => s.id),
          ...(side.spec.groups ?? []).map((g) => g.id),
        ];
        const boxes: Record<string, Box> = {};
        for (const id of ids) {
          const el = svg.querySelector(`[id$="-service-${id}"], [id$="-group-${id}"]`);
          if (!el) continue;
          const r = el.getBoundingClientRect();
          if (r.width === 0) continue;
          boxes[id] = {
            x: r.left - origin.left,
            y: r.top - origin.top,
            w: r.width,
            h: r.height,
          };
        }
        if (Object.keys(boxes).length === 0) done = false;
        return { boxes, w: origin.width, h: origin.height };
      });
      setMeasures(next);
      return done;
    };

    // mermaid is a lazy ~2.9MB chunk that draws after this mounts, and there is
    // no event to await — the figure only flips to `data-state="diagram"` when
    // it is done. So rather than trust a MutationObserver to catch the draw, poll
    // until every pane has measurable boxes and then stop, with a hard ceiling so
    // a diagram that never renders cannot spin forever.
    let timer = 0;
    const tick = (): void => {
      if (measure() && timer) {
        window.clearInterval(timer);
        timer = 0;
      }
    };
    const frame = requestAnimationFrame(tick);
    timer = window.setInterval(tick, 250);
    const ceiling = window.setTimeout(() => {
      if (timer) window.clearInterval(timer);
      timer = 0;
    }, 12000);

    const onResize = (): void => {
      measure();
    };
    window.addEventListener("resize", onResize);

    // A browser/page ZOOM (ctrl +/-, pinch, or a devicePixelRatio change) scales
    // every CSS-pixel measurement but does NOT reliably raise a `resize` event, so
    // the box coordinates kept describing the pre-zoom layout while the camera read
    // `stage.clientWidth` live — the two frames no longer agreed and the focus
    // drifted or clipped. A ResizeObserver on each pane's SVG fires whenever that
    // element's own box changes, which is exactly what a zoom does, so the snapshot
    // is retaken and the camera recomputes against matching geometry.
    const panes = paneRefs.current.filter(Boolean) as HTMLDivElement[];
    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => {
        measure();
        // The SVG resizing also means the pin/track geometry moved, so anchor the
        // scroll to the same step as well as retaking the box snapshot.
        remeasureRef.current?.();
      });
      for (const pane of panes) {
        const svg = pane.querySelector("svg");
        if (svg) observer.observe(svg);
      }
    }

    // devicePixelRatio is the other half: a zoom can change it (and a bare
    // resolution change can change it without moving any element), and there is
    // no event for it, so watch the media query that describes it.
    const dpr = window.devicePixelRatio || 1;
    const dprQuery =
      typeof window.matchMedia === "function"
        ? window.matchMedia(`(resolution: ${dpr}dppx)`)
        : null;
    const onDpr = (): void => {
      measure();
      remeasureRef.current?.();
    };
    dprQuery?.addEventListener("change", onDpr);

    return () => {
      cancelAnimationFrame(frame);
      if (timer) window.clearInterval(timer);
      window.clearTimeout(ceiling);
      window.removeEventListener("resize", onResize);
      observer?.disconnect();
      dprQuery?.removeEventListener("change", onDpr);
    };
  }, [sides, mode]);

  /* ── the scroll binding ────────────────────────────────────────────── */

  useEffect(() => {
    if (mode === "static") return;
    const track = trackRef.current;
    const pin = pinRef.current;
    if (!track || !pin) return;

    let distance = 0;
    let frame = 0;

    const measureTrack = () => {
      distance = Math.round(window.innerHeight * vhPerStep);
      track.style.height = `${pin.offsetHeight + distance}px`;
    };

    /**
     * Re-measure the track WITHOUT moving the reader.
     *
     * The track's height depends on `window.innerHeight`, so a viewport or zoom
     * change resizes it — and because the track sits at a fixed document offset,
     * its top edge and every step's scroll position move with it. Left alone that
     * lands the reader on a different step of the walk, which is what "it moves
     * around as I zoom" was. So read the current step first, resize, then put the
     * scroll position back on the same step.
     */
    const remeasure = () => {
      const pinEl = pinRef.current;
      const trackEl = trackRef.current;
      if (!pinEl || !trackEl) {
        measureTrack();
        update();
        return;
      }
      // The fraction of the walk the reader is currently on, before the
      // resize — UNCLAMPED. At or past either edge the walk does not hold
      // the pin, so the reader is just scrolling the page and must not be
      // moved at all. That bail is what stops the scroll-jump-on-load: on a
      // fresh load the pin sits far below the viewport (fraction 0) while
      // late layout (fonts, mermaid draw, the chat iframe) fires the pane
      // observers, and without it every one of those callbacks scrollTo'd
      // the tour start.
      const beforeAvail = Math.max(1, trackEl.offsetHeight - pinEl.offsetHeight);
      const beforeTop = trackEl.getBoundingClientRect().top + window.scrollY;
      const beforeRaw = (pinOffset() - beforeTop) / beforeAvail;

      measureTrack();

      if (!(beforeRaw > 0 && beforeRaw < 1)) {
        update();
        return;
      }
      const beforeP = clamp01(beforeRaw);

      // After the resize, put the scroll back so the same fraction sits under the
      // pin. Only do it while the walk actually holds the pin — outside it the
      // reader is just scrolling the page and must not be moved at all.
      const afterAvail = Math.max(1, trackEl.offsetHeight - pinEl.offsetHeight);
      const afterTop = trackEl.getBoundingClientRect().top + window.scrollY;
      const target = afterTop - pinOffset() + beforeP * afterAvail;
      // A zoom keeps the anchor scrollY ratio, so the browser may already be at
      // the right place; only nudge when the step would actually change.
      if (Math.abs(window.scrollY - target) > 2) {
        window.scrollTo({ top: Math.max(0, Math.round(target)), behavior: "auto" });
      }
      update();
    };

    const update = () => {
      // The pinned scroll IS the track minus the pin, so progress is measured
      // against that rather than against the requested budget — otherwise the
      // pin releases with the walk only partly finished and the last steps are
      // crammed into the tail.
      const avail = Math.max(1, track.offsetHeight - pin.offsetHeight);
      const p = clamp01((pinOffset() - track.getBoundingClientRect().top) / avail);
      pin.style.setProperty("--arch-p", p.toFixed(4));

      // Each rail's own progress bar would otherwise read the whole-walk value:
      // on the rented rail that fills only its share then the side slides away,
      // and on the owned rail it is already full before that side starts. So
      // each side gets a local 0→1 across its own steps.
      let seen = 0;
      for (let si = 0; si < sides.length; si += 1) {
        const total = sides[si].steps.length;
        const local = clamp01((p * count - seen) / Math.max(1, total));
        pin.style.setProperty(`--arch-r${si}`, local.toFixed(4));
        seen += total;
      }

      // The swipe lives in the tail of the last step of the earlier side, so the
      // reader finishes that walk before the page changes diagram under them.
      const v = p * count;
      const index = Math.min(count - 1, Math.floor(v));
      const frac = clamp01(v - index);
      let swap = 0;
      if (sides.length > 1) {
        if (index >= swapAt) swap = 1;
        else if (index === swapAt - 1) swap = smooth((frac - 0.35) / 0.65);
      }
      const grid = gridRef.current;
      if (grid) {
        // "get rid of the old, in with the new": the rented group leaves over
        // the first half of the window and the owned group arrives over the
        // second, so the two are never in the frame together and nothing has to
        // be faded to hide the hand-off.
        grid.style.setProperty("--arch-out", clamp01(swap * 2).toFixed(4));
        grid.style.setProperty("--arch-in", clamp01(swap * 2 - 1).toFixed(4));
      }

      setStep((current) => (current === index ? current : index));
    };

    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    const onResize = () => {
      remeasure();
    };

    remeasureRef.current = remeasure;
    measureTrack();
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);

    /* ── one gesture, one step ─────────────────────────────────────────
       Without this the walk is pure position: a single trackpad flick keeps
       feeding scroll events and carries the reader through every step at once.
       So while the pin is held we take the wheel/touch gesture and advance
       EXACTLY one step, then lock for the settle window. A gesture that arrives
       outside the pin, or once the walk is finished and the pin about to
       release, is left alone so the page never traps the reader.

       The lock is deliberately generous: it has to outlast the smooth scroll
       below (which is longer now) so a second flick in the same movement is
       swallowed rather than advancing again — that is what makes the walk read
       as continuous instead of jumpy. */
    const GESTURE_COOLDOWN_MS = 1250;
    let lockUntil = 0;

    const avail = () => Math.max(1, track.offsetHeight - pin.offsetHeight);

    const stepScrollTop = (next: number) => {
      const trackTop = track.getBoundingClientRect().top + window.scrollY;
      const target = trackTop - pinOffset() + (next / count) * avail();
      return Math.max(0, Math.round(target));
    };

    const pinned = () => {
      const p = clamp01((pinOffset() - track.getBoundingClientRect().top) / avail());
      return p > 0 && p < 1;
    };

    const nudge = (dir: number) => {
      const now = performance.now();
      if (now < lockUntil) return true;
      if (!pinned()) return false;
      const p = clamp01((pinOffset() - track.getBoundingClientRect().top) / avail());
      const current = Math.min(count - 1, Math.floor(p * count));
      const next = Math.max(0, Math.min(count - 1, current + dir));
      // At either end, hand the gesture back to the page so the reader can
      // leave the band by continuing to scroll.
      if (next === current) return false;
      lockUntil = now + GESTURE_COOLDOWN_MS;
      window.scrollTo({ top: stepScrollTop(next + 0.5), behavior: "smooth" });
      return true;
    };

    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) < 2 || event.ctrlKey) return;
      if (nudge(event.deltaY > 0 ? 1 : -1)) event.preventDefault();
    };
    let touchStartY = 0;
    const onTouchStart = (event: TouchEvent) => {
      touchStartY = event.touches[0]?.clientY ?? 0;
    };
    const onTouchMove = (event: TouchEvent) => {
      const dy = touchStartY - (event.touches[0]?.clientY ?? 0);
      if (Math.abs(dy) < 24) return;
      if (nudge(dy > 0 ? 1 : -1)) event.preventDefault();
      touchStartY = event.touches[0]?.clientY ?? 0;
    };

    pin.addEventListener("wheel", onWheel, { passive: false });
    pin.addEventListener("touchstart", onTouchStart, { passive: true });
    pin.addEventListener("touchmove", onTouchMove, { passive: false });

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      pin.removeEventListener("wheel", onWheel);
      pin.removeEventListener("touchstart", onTouchStart);
      pin.removeEventListener("touchmove", onTouchMove);
      track.style.height = "";
    };
  }, [mode, count, swapAt, sides.length, vhPerStep]);

  // The diagrams arrive after mermaid draws, so the pin is taller than it was
  // when the track was first measured — remeasure once the boxes land.
  useEffect(() => {
    if (measures.length === 0) return;
    remeasureRef.current();
  }, [measures]);

  /* ── the camera ────────────────────────────────────────────────────── */

  const active = flat[Math.min(step, count - 1)];
  const activeSide = active?.side ?? 0;
  const activeIds = mode === "static" ? [] : (active?.ids ?? []);

  useEffect(() => {
    const stage = stageRef.current;
    // The camera is only ever on the LAST side: the first side is walked with the
    // glow alone, so the swipe is the moment the page starts moving. A camera on
    // a walk whose sets grow from one box to all of them could only zoom in and
    // then have to pull back out, which is what read as broken.
    const camSide = sides.length - 1;
    cameraRefs.current.forEach((camera, si) => {
      if (!camera) return;
      const off = (): void => {
        camera.style.transform = "";
      };
      if (mode !== "camera" || si !== camSide || activeSide !== camSide || activeIds.length === 0) {
        off();
        return;
      }
      const m = measures[si];
      if (!m || !m.w || !m.h) {
        off();
        return;
      }
      const picked = activeIds.map((id) => m.boxes[id]).filter(Boolean) as Box[];
      if (picked.length === 0) {
        off();
        return;
      }
      const stageW = stage?.clientWidth ?? 0;
      const stageH = stage?.clientHeight ?? 0;
      if (!stageW || !stageH) {
        off();
        return;
      }

      // The snapshot's box coordinates are CSS pixels measured at whatever the
      // zoom was when `measure()` last ran. The stage below is read live, so if a
      // zoom has resized the diagram since, the two are on different scales and
      // the transform lands off-target. Re-read the pane's own SVG and, when it
      // disagrees with the snapshot, scale the snapshot's coordinates onto the
      // current size so the camera still frames the same boxes.
      const svg = paneRefs.current[si]?.querySelector("svg");
      const liveW = svg?.getBoundingClientRect().width ?? 0;
      let scale = 1;
      let contentW = m.w;
      let contentH = m.h;
      if (svg && liveW > 0 && Math.abs(liveW - m.w) > 0.5) {
        scale = liveW / m.w;
        contentW = m.w * scale;
        contentH = m.h * scale;
      }
      const metrics = picked.map((b) => ({
        x: b.x * scale,
        y: b.y * scale,
        w: b.w * scale,
        h: b.h * scale,
      }));

      const minX = Math.min(...metrics.map((b) => b.x));
      const minY = Math.min(...metrics.map((b) => b.y));
      const maxX = Math.max(...metrics.map((b) => b.x + b.w));
      const maxY = Math.max(...metrics.map((b) => b.y + b.h));
      const width = Math.max(maxX - minX, 1);
      const height = Math.max(maxY - minY, 1);

      // Fill at most about a third of the frame with the target, and never zoom
      // out. The cap matters more than the fraction: a two-box step whose union
      // is 105px wide inside a 734px stage would otherwise peg the zoom and crop
      // the architecture out of the frame entirely.
      const k = Math.max(1, Math.min(1.45, 0.34 * Math.min(stageW / width, stageH / height)));
      if (k < 1.02) {
        off();
        return;
      }

      // Centre the target, then clamp the pan so the scaled diagram always
      // covers the stage. Without this clamp a target near an edge pulls the
      // opposite edge of the diagram in and leaves a bare gap in the frame,
      // which is what made the camera look broken.
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      const pan = (span: number, content: number, centre: number): number => {
        const low = span / k - content;
        if (low > 0) return low / 2;
        return Math.min(0, Math.max(low, span / (2 * k) - centre));
      };

      camera.style.transform = `scale(${k.toFixed(4)}) translate(${pan(stageW, contentW, cx).toFixed(2)}px, ${pan(stageH, contentH, cy).toFixed(2)}px)`;
    });
  }, [mode, activeSide, activeIds, measures]);

  /* ── render ────────────────────────────────────────────────────────── */

  if (mode === "static") {
    return (
      <div className={`arch-tour${className ? ` ${className}` : ""}`} data-variant="static">
        {sides.map((side, si) => (
          <div className="arch-tour__static" key={si}>
            {side.tag ? <span className="arch-tour__tag" data-tag={side.tag}>{side.tag}</span> : null}
            <ArchitectureDiagram spec={side.spec} caption={side.caption} />
            <ol className="arch-tour__rail">
              {side.steps.map((entry, index) => (
                <li className="arch-tour__step" key={entry.id}>
                  <span className="arch-tour__index">{String(index + 1).padStart(2, "0")}</span>
                  <span className="arch-tour__label">{entry.label}</span>
                  <span className="arch-tour__line">{entry.line}</span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={`arch-tour${className ? ` ${className}` : ""}`} data-variant={mode}>
      <div className="arch-tour__track" ref={trackRef}>
        <div className="arch-tour__pin" ref={pinRef}>
          {header ? <div className="arch-tour__head">{header}</div> : null}
          <div className="arch-tour__grid" ref={gridRef}>
            {sides.map((side, si) => {
              const base = sides.slice(0, si).reduce((n, s) => n + s.steps.length, 0);
              const mod =
                sides.length > 1
                  ? si === 0
                    ? " arch-tour__side--leaving"
                    : " arch-tour__side--entering"
                  : "";
              return (
                <div className={`arch-tour__side${mod}`} key={si} data-rail={side.rail ?? "start"}>
                  <div className="arch-tour__frame">
                    <div className="arch-tour__stage" ref={si === 0 ? stageRef : undefined}>
                      <div
                        className="arch-tour__pane"
                        ref={(el) => {
                          paneRefs.current[si] = el;
                        }}
                      >
                        <div
                          className="arch-tour__camera"
                          ref={(el) => {
                            cameraRefs.current[si] = el;
                          }}
                        >
                          <ArchitectureDiagram spec={side.spec} lit={si === activeSide ? activeIds : undefined} />
                          {si === activeSide ? (() => {
                            // ONE spotlight over the union of the lit boxes, never
                            // one per box: each `.arch-tour__spot` carries a 9999px
                            // dim shadow, so N spots stack that dim N times and the
                            // last rented steps — which light most of the diagram —
                            // went to near-black and read as an unreadable blur.
                            const lit0 = activeIds
                              .map((id) => measures[si]?.boxes[id])
                              .filter(Boolean) as Box[];
                            if (lit0.length === 0) return null;
                            const minX = Math.min(...lit0.map((b) => b.x));
                            const minY = Math.min(...lit0.map((b) => b.y));
                            const maxX = Math.max(...lit0.map((b) => b.x + b.w));
                            const maxY = Math.max(...lit0.map((b) => b.y + b.h));
                            const pad = 6;
                            return (
                              <span
                                className="arch-tour__spot"
                                aria-hidden="true"
                                style={{
                                  left: `${minX - pad}px`,
                                  top: `${minY - pad}px`,
                                  width: `${maxX - minX + pad * 2}px`,
                                  height: `${maxY - minY + pad * 2}px`,
                                }}
                              />
                            );
                          })() : null}
                        </div>
                      </div>
                    </div>
                  </div>

                  {side.tag ? (
                    <span className="arch-tour__side-tag" data-tag={side.tag}>{side.tag}</span>
                  ) : null}
                  <ol className="arch-tour__rail">
                    {side.steps.map((entry, index) => {
                      const on = base + index === step;
                      return (
                        <li className={`arch-tour__step${on ? " on" : ""}`} key={entry.id}>
                          <span className="arch-tour__index">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <span className="arch-tour__label">{entry.label}</span>
                          <span className="arch-tour__line">{entry.line}</span>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
