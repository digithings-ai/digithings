"use client";
/**
 * Architecture tour — the same container diagram, walked.
 *
 * The owner's ask: "at the beginning we show the full diagram and as we go
 * through every step we kind of have this guided view as we walk through the
 * diagram ... one that's more static, that's just full view, one that's animated
 * with the scroll but it just highlights the different cards, one that follows
 * the cards around so with a scale of ... from fully static to very motion
 * animated."
 *
 * So the same spec and the same steps render in three treatments, chosen by
 * `variant`:
 *
 *   static     the whole diagram, full view, the steps listed beside it
 *   highlight  pinned; scrolling advances the step, and the boxes that step is
 *              about get a ring
 *   camera     pinned; as well as the ring, the frame pans and zooms so the
 *              active boxes sit in the middle — step 0 is the full view, so the
 *              move always starts wide and comes in
 *
 * HOW IT KNOWS WHERE ANYTHING IS. It does not. mermaid's layout is its own, so
 * the tour measures the rendered SVG after the fact: each service is emitted as
 * `<g id="arch-…-service-<id>">` and each boundary as `<g id="arch-…-group-<id>">`,
 * which makes every box addressable by id without touching mermaid internals or
 * hard-coding coordinates. Measurements are taken once the SVG appears (a
 * MutationObserver on the stage) and again on resize, always while the camera is
 * untransformed so the numbers are in unscaled stage space.
 *
 * MOTION BUDGET. One rAF-throttled passive scroll listener writing ONE custom
 * property; React state changes only when the coarse step index changes. Reduced
 * motion gets the static treatment, and so does anything narrower than the
 * breakpoint at which the pinned layout fits.
 */

import { useEffect, useRef, useState } from "react";

import { ArchitectureDiagram, type ArchSpec } from "./ArchitectureDiagram";

export interface TourStep {
  id: string;
  label: string;
  line: string;
  /** Box ids this step is about. Empty means "the whole diagram". */
  ids: string[];
}

export type TourVariant = "static" | "highlight" | "camera";

export interface ArchitectureTourProps {
  spec: ArchSpec;
  steps: TourStep[];
  variant?: TourVariant;
  /** Scroll spent per step, in viewport heights. */
  vhPerStep?: number;
  caption?: string;
  className?: string;
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

const NO_MOTION = "(prefers-reduced-motion: reduce)";
const PIN_MEDIA = "(min-width: 960px)";

const clamp01 = (n: number): number => Math.max(0, Math.min(1, n));

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
  spec,
  steps,
  variant = "static",
  vhPerStep = 0.62,
  caption,
  className,
}: ArchitectureTourProps) {
  const reduced = usePrefersReducedMotion();
  const wide = usePinned();
  // The two animated treatments need a pin to exist; without one they read as
  // the static treatment rather than pinning to nothing.
  const mode: TourVariant = reduced || !wide ? "static" : variant;

  const trackRef = useRef<HTMLDivElement | null>(null);
  const pinRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const cameraRef = useRef<HTMLDivElement | null>(null);
  /** Set by the scroll effect so a late-arriving SVG can resize the track. */
  const remeasureRef = useRef<() => void>(() => {});

  const [boxes, setBoxes] = useState<Record<string, Box>>({});
  const [step, setStep] = useState(0);

  /* ── measure the rendered diagram ──────────────────────────────────── */

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const ids = [...spec.services.map((s) => s.id), ...(spec.groups ?? []).map((g) => g.id)];

    const measure = () => {
      const svg = stage.querySelector("svg");
      if (!svg) return;
      const origin = svg.getBoundingClientRect();
      if (origin.width === 0) return;
      const next: Record<string, Box> = {};
      for (const id of ids) {
        const el = svg.querySelector(`[id$="-service-${id}"], [id$="-group-${id}"]`);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        if (r.width === 0) continue;
        next[id] = {
          x: r.left - origin.left,
          y: r.top - origin.top,
          w: r.width,
          h: r.height,
        };
      }
      setBoxes(next);
    };

    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };

    // The SVG arrives after mermaid has parsed and drawn, so watch for it.
    const observer = new MutationObserver(schedule);
    observer.observe(stage, { childList: true, subtree: true });
    schedule();

    window.addEventListener("resize", schedule);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", schedule);
      cancelAnimationFrame(frame);
    };
  }, [spec]);

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
      const p = distance > 0 ? clamp01((pinOffset() - track.getBoundingClientRect().top) / distance) : 0;
      pin.style.setProperty("--arch-p", p.toFixed(4));
      const next = Math.min(steps.length - 1, Math.floor(p * steps.length));
      setStep((current) => (current === next ? current : next));
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
  }, [mode, steps.length, vhPerStep]);

  // The diagram arrives after mermaid draws, so the pin is taller than it was
  // when the track was first measured — remeasure once the boxes land.
  useEffect(() => {
    if (Object.keys(boxes).length === 0) return;
    remeasureRef.current();
  }, [boxes]);

  /* ── the camera ────────────────────────────────────────────────────── */

  const active = steps[Math.min(step, steps.length - 1)];
  const activeIds = mode === "static" ? [] : (active?.ids ?? []);

  useEffect(() => {
    const camera = cameraRef.current;
    const stage = stageRef.current;
    if (!camera || !stage) return;

    if (mode !== "camera" || activeIds.length === 0) {
      camera.style.transform = "";
      camera.style.removeProperty("--arch-k");
      return;
    }

    const picked = activeIds.map((id) => boxes[id]).filter(Boolean);
    if (picked.length === 0) return;

    const minX = Math.min(...picked.map((b) => b.x));
    const minY = Math.min(...picked.map((b) => b.y));
    const maxX = Math.max(...picked.map((b) => b.x + b.w));
    const maxY = Math.max(...picked.map((b) => b.y + b.h));
    const width = Math.max(maxX - minX, 1);
    const height = Math.max(maxY - minY, 1);
    const stageW = stage.clientWidth;
    const stageH = stage.clientHeight;
    if (!stageW || !stageH) return;

    // Fill at most ~55% of the frame with the target, and never zoom out.
    const k = Math.max(1, Math.min(2.2, 0.42 * Math.min(stageW / width, stageH / height)));
    // A step whose boxes already fill the frame cannot be zoomed into, and
    // translating at k = 1 would only shove the layout off-centre. Stay put.
    if (k < 1.02) {
      camera.style.transform = "";
      camera.style.removeProperty("--arch-k");
      return;
    }
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    camera.style.setProperty("--arch-k", k.toFixed(4));
    camera.style.transform = `scale(${k.toFixed(4)}) translate(${(stageW / (2 * k) - cx).toFixed(2)}px, ${(stageH / (2 * k) - cy).toFixed(2)}px)`;
  }, [mode, activeIds, boxes]);

  /* ── render ────────────────────────────────────────────────────────── */

  const spots = mode === "static" ? [] : activeIds;

  const rail = (
    <ol className="arch-tour__rail">
      {steps.map((entry, index) => {
        const on = mode !== "static" && index === step;
        return (
          <li className={`arch-tour__step${on ? " on" : ""}`} key={entry.id}>
            <span className="arch-tour__index">{String(index + 1).padStart(2, "0")}</span>
            <span className="arch-tour__label">{entry.label}</span>
            <span className="arch-tour__line">{entry.line}</span>
          </li>
        );
      })}
    </ol>
  );

  const frame = (
    <div className="arch-tour__frame">
      <div className="arch-tour__stage" ref={stageRef}>
        <div className="arch-tour__camera" ref={cameraRef}>
          <ArchitectureDiagram spec={spec} caption={caption} />
        </div>
        {spots.map((id) => {
          const box = boxes[id];
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
        })}
      </div>
    </div>
  );

  if (mode === "static") {
    return (
      <div className={`arch-tour${className ? ` ${className}` : ""}`} data-variant="static">
        {frame}
        {rail}
      </div>
    );
  }

  return (
    <div className={`arch-tour${className ? ` ${className}` : ""}`} data-variant={mode}>
      <div className="arch-tour__track" ref={trackRef}>
        <div className="arch-tour__pin" ref={pinRef}>
          <div className="arch-tour__grid">
            {frame}
            {rail}
          </div>
        </div>
      </div>
    </div>
  );
}
