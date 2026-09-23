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
 *   - the last fraction of the final step slides the first diagram off and the
 *     second one in;
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
 * MOTION BUDGET. One rAF-throttled passive scroll listener writing ONE custom
 * property (`--arch-swap` on the strip; `--arch-p` on the pin); React state
 * changes only when the coarse step index changes. Reduced motion gets the
 * static treatment, and so does anything narrower than the breakpoint at which
 * the pinned layout fits.
 */

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

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
}

export type TourVariant = "static" | "highlight" | "camera";

export interface ArchitectureTourProps {
  /** One side is a plain walk; two add the swipe between them. */
  sides: TourSide[];
  variant?: TourVariant;
  /** Scroll spent per step, in viewport heights. */
  vhPerStep?: number;
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
const PIN_MEDIA = "(min-width: 960px)";

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
  vhPerStep = 0.8,
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
  const stripRef = useRef<HTMLDivElement | null>(null);
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

    return () => {
      cancelAnimationFrame(frame);
      if (timer) window.clearInterval(timer);
      window.clearTimeout(ceiling);
      window.removeEventListener("resize", onResize);
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

    const update = () => {
      // The pinned scroll IS the track minus the pin, so progress is measured
      // against that rather than against the requested budget — otherwise the
      // pin releases with the walk only partly finished and the last steps are
      // crammed into the tail.
      const avail = Math.max(1, track.offsetHeight - pin.offsetHeight);
      const p = clamp01((pinOffset() - track.getBoundingClientRect().top) / avail);
      pin.style.setProperty("--arch-p", p.toFixed(4));

      // The swipe lives in the tail of the last step of the earlier side, so the
      // reader finishes that walk before the page changes diagram under them.
      const v = p * count;
      const index = Math.min(count - 1, Math.floor(v));
      const frac = clamp01(v - index);
      let swap = 0;
      if (sides.length > 1) {
        if (index >= swapAt) swap = 1;
        else if (index === swapAt - 1) swap = smooth((frac - 0.5) / 0.5);
      }
      stripRef.current?.style.setProperty("--arch-swap", swap.toFixed(4));

      setStep((current) => (current === index ? current : index));
    };

    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    const onResize = () => {
      measureTrack();
      update();
    };

    remeasureRef.current = measureTrack;
    measureTrack();
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
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

      const minX = Math.min(...picked.map((b) => b.x));
      const minY = Math.min(...picked.map((b) => b.y));
      const maxX = Math.max(...picked.map((b) => b.x + b.w));
      const maxY = Math.max(...picked.map((b) => b.y + b.h));
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

      camera.style.transform = `scale(${k.toFixed(4)}) translate(${pan(stageW, m.w, cx).toFixed(2)}px, ${pan(stageH, m.h, cy).toFixed(2)}px)`;
    });
  }, [mode, activeSide, activeIds, measures]);

  /* ── render ────────────────────────────────────────────────────────── */

  if (mode === "static") {
    return (
      <div className={`arch-tour${className ? ` ${className}` : ""}`} data-variant="static">
        {sides.map((side, si) => (
          <div className="arch-tour__static" key={si}>
            {side.tag ? <span className="arch-tour__tag">{side.tag}</span> : null}
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

  const stageStyle = { "--sides": String(sides.length) } as CSSProperties;

  return (
    <div className={`arch-tour${className ? ` ${className}` : ""}`} data-variant={mode}>
      <div className="arch-tour__track" ref={trackRef}>
        <div className="arch-tour__pin" ref={pinRef}>
          <div className="arch-tour__grid">
            <div className="arch-tour__frame">
              <div className="arch-tour__stage" ref={stageRef} style={stageStyle}>
                <div className="arch-tour__strip" ref={stripRef}>
                  {sides.map((side, si) => (
                    <div
                      className="arch-tour__pane"
                      key={si}
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
                        <ArchitectureDiagram spec={side.spec} />
                        {si === activeSide
                          ? activeIds.map((id) => {
                              const box = measures[si]?.boxes[id];
                              if (!box) return null;
                              return (
                                <span
                                  className="arch-tour__spot"
                                  key={id}
                                  aria-hidden="true"
                                  style={{
                                    left: `${box.x}px`,
                                    top: `${box.y}px`,
                                    width: `${box.w}px`,
                                    height: `${box.h}px`,
                                  }}
                                />
                              );
                            })
                          : null}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <ol className="arch-tour__rail">
              {flat.map((entry, index) => {
                const on = index === step;
                const first = index === 0 || flat[index - 1].side !== entry.side;
                return (
                  <li
                    className={`arch-tour__step${on ? " on" : ""}`}
                    key={`${entry.side}-${entry.id}`}
                    data-side={entry.side}
                  >
                    <span className="arch-tour__index">
                      {first && sides[entry.side]?.tag ? (
                        <span className="arch-tour__side-tag">{sides[entry.side].tag}</span>
                      ) : null}
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="arch-tour__label">{entry.label}</span>
                    <span className="arch-tour__line">{entry.line}</span>
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
