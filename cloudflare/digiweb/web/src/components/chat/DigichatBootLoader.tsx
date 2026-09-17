"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

/**
 * DigichatBootLoader — the default DigiChat loading animation.
 *
 * A field of 3px cubes rides the composer outline: two heads start in
 * opposite corners and sweep out-and-back (lighting cubes on the way out,
 * clearing them on the way back) until the consumer reports `ready`.
 * The heads then refill the outline to their far corners and park, the
 * cube layer hands off to the composer's 1px border, and the welcome copy,
 * suggestion rows, attachment glyph and send glyph type/build in.
 *
 * Pace and geometry are ported from the approved demo (loading-demos G6):
 * 3px cubes on a 4px pitch, six cubes per head per 32ms tick.
 * Styles: @digithings/web/styles/digichat-boot-loader.css.
 */

/** 5x5 cube geometry, mirroring DotMatrix so every glyph reads identically. */
const GRID = 5;
const CELL_SIZE = 2.3;
const CELL_PITCH = 4;
const CELL_OFFSET = 0.85;

/** Loader pace: 3px cubes on a 4px pitch, six cubes per head per tick. */
const CFG = { SIZE: 3, PITCH: 4, TICK_MS: 32, STEP: 6 } as const;

type Dot = readonly [number, number];
const cellIndex = (row: number, col: number) => row * GRID + col;
const cellsFrom = (dots: readonly Dot[]) => dots.map(([row, col]) => cellIndex(row, col));

/** DotMatrix state glyphs rendered while the composer settles. */
const SEND_CELLS = cellsFrom([
  [0, 2],
  [0, 3],
  [0, 4],
  [1, 4],
  [2, 1],
  [2, 4],
  [3, 0],
  [3, 1],
  [3, 2],
  [3, 3],
  [3, 4],
  [4, 1],
]);
const PLUS_CELLS = cellsFrom([
  [1, 2],
  [2, 1],
  [2, 2],
  [2, 3],
  [3, 2],
]);
const EXAMPLE_CELLS = cellsFrom([
  [1, 2],
  [2, 1],
  [2, 3],
  [3, 2],
]);

const DEFAULT_WELCOME = "Ask a question";
const DEFAULT_WELCOME_BODY = "Ask about anything you need help with.";
const DEFAULT_PLACEHOLDER = "Ask a question";
const DEFAULT_SUGGESTIONS = [
  "What can you help me with?",
  "Search my workspace",
  "Connect a tool",
  "Change the appearance",
];

/** Settle timeline (ms after both heads park). */
const SETTLE = {
  HIDE_GRID: 280,
  SOLID: 340,
  POP: 640,
  PLACEHOLDER: 700,
  SEND: 760,
  WELCOME: 860,
  CHIPS: 1060,
  BODY: 1300,
  DONE: 2400,
} as const;

/** Typewriter speeds (ms per character), matching the approved demo. */
const TYPE = { PLACEHOLDER: 34, SEND_BUILD: 48, WELCOME: 32, CHIP: 12, BODY: 22 } as const;

function Glyph({ cells, className }: { cells: readonly number[]; className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false" shapeRendering="crispEdges" className={className}>
      {cells.map((cell) => {
        const row = Math.floor(cell / GRID);
        const col = cell % GRID;
        return (
          <rect
            key={`${row}-${col}`}
            x={CELL_OFFSET + col * CELL_PITCH}
            y={CELL_OFFSET + row * CELL_PITCH}
            width={CELL_SIZE}
            height={CELL_SIZE}
            fill="currentColor"
          />
        );
      })}
    </svg>
  );
}

function TypedText({
  text,
  active,
  speedMs,
  delayMs = 0,
  instant = false,
}: {
  text: string;
  active: boolean;
  speedMs: number;
  delayMs?: number;
  instant?: boolean;
}) {
  const [count, setCount] = useState(instant ? text.length : 0);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (instant) {
      setCount(text.length);
      return;
    }
    if (!active) return;
    let interval: number | undefined;
    const timeout = window.setTimeout(() => {
      setStarted(true);
      interval = window.setInterval(() => {
        setCount((current) => {
          if (current >= text.length) {
            if (interval !== undefined) window.clearInterval(interval);
            return current;
          }
          return current + 1;
        });
      }, speedMs);
    }, delayMs);
    return () => {
      window.clearTimeout(timeout);
      if (interval !== undefined) window.clearInterval(interval);
    };
  }, [active, delayMs, instant, speedMs, text]);

  if (instant) return <>{text}</>;
  return (
    <>
      {text.slice(0, count)}
      {started && count < text.length ? <span className="dboot-caret" aria-hidden="true" /> : null}
    </>
  );
}

function BuildingGlyph({
  cells,
  active,
  speedMs,
  delayMs = 0,
  instant = false,
  className,
}: {
  cells: readonly number[];
  active: boolean;
  speedMs: number;
  delayMs?: number;
  instant?: boolean;
  className?: string;
}) {
  const [count, setCount] = useState(instant ? cells.length : 0);

  useEffect(() => {
    if (instant) {
      setCount(cells.length);
      return;
    }
    if (!active) return;
    let interval: number | undefined;
    const timeout = window.setTimeout(() => {
      interval = window.setInterval(() => {
        setCount((current) => {
          if (current >= cells.length) {
            if (interval !== undefined) window.clearInterval(interval);
            return current;
          }
          return current + 1;
        });
      }, speedMs);
    }, delayMs);
    return () => {
      window.clearTimeout(timeout);
      if (interval !== undefined) window.clearInterval(interval);
    };
  }, [active, cells.length, delayMs, instant, speedMs]);

  if (instant) return <Glyph cells={cells} className={className} />;
  if (count === 0) return null;
  return <Glyph cells={cells.slice(0, count)} className={className} />;
}

interface BorderCube {
  rect: SVGRectElement;
  lit: boolean;
  op: number;
}

interface BorderEngine {
  start: () => void;
  rebuild: () => void;
  finish: () => void;
  destroy: () => void;
}

function createBorderEngine({
  wrap,
  svg,
  onParked,
}: {
  wrap: HTMLElement;
  svg: SVGSVGElement;
  onParked: () => void;
}): BorderEngine {
  let cubes: BorderCube[] = [];
  let headEls: SVGRectElement[] = [];
  let width = 0;
  let height = 0;
  let litCount = 0;
  let mode: "warm" | "finish" = "warm";
  let cornerA = 0;
  let cornerB = 0;
  let tickId: number | null = null;
  let rafId: number | null = null;
  let destroyed = false;
  const pos: [number, number] = [0, 0];
  const phase: Array<"out" | "back"> = ["out", "out"];
  const parked = [false, false];

  function draw() {
    for (const cube of cubes) {
      const op = cube.lit ? 1 : 0;
      if (op !== cube.op) {
        cube.op = op;
        cube.rect.style.opacity = String(op);
      }
    }
  }

  function setHeads() {
    for (const el of headEls) el.classList.remove("fhead");
    headEls = pos
      .map((index) => (cubes[index] ? cubes[index].rect : null))
      .filter((el): el is SVGRectElement => el !== null);
    for (const el of headEls) el.classList.add("fhead");
  }

  function build() {
    const nextWidth = Math.round(wrap.clientWidth);
    const nextHeight = Math.round(wrap.clientHeight);
    if (!nextWidth || !nextHeight) return false;
    width = nextWidth;
    height = nextHeight;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const size = CFG.SIZE;
    const pitch = CFG.PITCH;
    const cols = Math.max(2, Math.round(width / pitch) + 1);
    const rows = Math.max(2, Math.round(height / pitch) + 1);
    const x = (i: number) => (i * width) / (cols - 1);
    const y = (j: number) => (j * height) / (rows - 1);
    const points: Array<[number, number]> = [];
    for (let i = 0; i < cols; i += 1) points.push([x(i), 0]);
    for (let j = 1; j < rows; j += 1) points.push([width, y(j)]);
    for (let i = cols - 2; i >= 0; i -= 1) points.push([x(i), height]);
    for (let j = rows - 2; j >= 1; j -= 1) points.push([0, y(j)]);
    cubes = points.map(([cx, cy]) => {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(cx - size / 2));
      rect.setAttribute("y", String(cy - size / 2));
      rect.setAttribute("width", String(size));
      rect.setAttribute("height", String(size));
      rect.style.opacity = "0";
      svg.appendChild(rect);
      return { rect, lit: false, op: 0 };
    });
    return true;
  }

  function tick() {
    if (destroyed) return;
    const count = cubes.length;
    if (!count) return;
    for (let head = 0; head < 2; head += 1) {
      if (parked[head]) continue;
      const far = head === 0 ? cornerB : cornerA;
      const anchor = head === 0 ? cornerA : cornerB;
      if (mode === "finish" && pos[head] === far) {
        parked[head] = true;
        continue;
      }
      let current = pos[head];
      for (let k = 0; k < CFG.STEP; k += 1) {
        if (phase[head] === "out") {
          const next = (current + 1) % count;
          current = next;
          const cube = cubes[next];
          if (cube && !cube.lit) {
            cube.lit = true;
            litCount += 1;
          }
          if (next === far) {
            if (mode === "finish") parked[head] = true;
            else phase[head] = "back";
            break;
          }
        } else {
          const leaving = cubes[current];
          if (leaving && leaving.lit) {
            leaving.lit = false;
            litCount -= 1;
          }
          current = (current - 1 + count) % count;
          if (current === anchor) {
            phase[head] = "out";
            break;
          }
        }
      }
      pos[head] = current;
    }
    setHeads();
    draw();
    if (mode === "finish" && parked[0] && parked[1]) {
      stop();
      onParked();
    }
  }

  function startTicker() {
    if (tickId !== null) window.clearInterval(tickId);
    tickId = window.setInterval(tick, CFG.TICK_MS);
  }

  function startRaf() {
    if (rafId !== null) return;
    const loop = () => {
      if (destroyed || rafId === null) return;
      draw();
      rafId = window.requestAnimationFrame(loop);
    };
    rafId = window.requestAnimationFrame(loop);
  }

  function stop() {
    if (tickId !== null) {
      window.clearInterval(tickId);
      tickId = null;
    }
    if (rafId !== null) {
      window.cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  function reset() {
    mode = "warm";
    litCount = 0;
    cornerA = 0;
    cornerB = Math.floor(cubes.length / 2);
    pos[0] = cornerA;
    pos[1] = cornerB;
    phase[0] = "out";
    phase[1] = "out";
    parked[0] = false;
    parked[1] = false;
    for (const index of pos) {
      const cube = cubes[index];
      if (cube && !cube.lit) {
        cube.lit = true;
        litCount += 1;
      }
    }
    setHeads();
    draw();
  }

  return {
    start() {
      if (destroyed) return;
      if (!build()) return;
      reset();
      startTicker();
      startRaf();
    },
    rebuild() {
      if (destroyed || mode === "finish") return;
      const nextWidth = Math.round(wrap.clientWidth);
      const nextHeight = Math.round(wrap.clientHeight);
      if (!nextWidth || !nextHeight) return;
      if (nextWidth === width && nextHeight === height) return;
      build();
      reset();
    },
    finish() {
      if (destroyed) return;
      if (!cubes.length) {
        stop();
        onParked();
        return;
      }
      mode = "finish";
      phase[0] = "out";
      phase[1] = "out";
    },
    destroy() {
      destroyed = true;
      stop();
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      cubes = [];
      headEls = [];
    },
  };
}

export interface DigichatBootLoaderProps {
  /** Flip true when the embed has painted; the loader then parks and hands off. */
  ready?: boolean;
  /** Fired after the settle + typewriter sequence finishes (or on ready in reduced motion). */
  onSettled?: () => void;
  welcome?: string;
  welcomeBody?: string;
  suggestions?: readonly string[];
  placeholder?: string;
  /** Accessible status text (visually hidden). */
  label?: string;
  /** Chat accent for the loader cursor; falls back to the accent/ink chain. */
  accent?: string;
  /** Render the attach plus glyph in the mock composer; mirrors the tenant attachments flag. */
  showAttachment?: boolean;
  className?: string;
}

export function DigichatBootLoader({
  ready = false,
  onSettled,
  welcome = DEFAULT_WELCOME,
  welcomeBody = DEFAULT_WELCOME_BODY,
  suggestions = DEFAULT_SUGGESTIONS,
  placeholder = DEFAULT_PLACEHOLDER,
  label = "Loading chat",
  accent,
  showAttachment = true,
  className,
}: DigichatBootLoaderProps) {
  const [reduced, setReduced] = useState(false);
  const [gridHidden, setGridHidden] = useState(false);
  const [lineUp, setLineUp] = useState(false);
  const [solid, setSolid] = useState(false);
  const [pop, setPop] = useState(false);
  const [chipsVisible, setChipsVisible] = useState(false);
  const [placeholderTyping, setPlaceholderTyping] = useState(false);
  const [welcomeTyping, setWelcomeTyping] = useState(false);
  const [bodyTyping, setBodyTyping] = useState(false);
  const [chipsTyping, setChipsTyping] = useState(false);
  const [sendBuilding, setSendBuilding] = useState(false);

  const wrapRef = useRef<HTMLDivElement | null>(null);
  const gridRef = useRef<SVGSVGElement | null>(null);
  const engineRef = useRef<BorderEngine | null>(null);
  const settleStartedRef = useRef(false);
  const timeoutsRef = useRef<number[]>([]);
  const onSettledRef = useRef(onSettled);

  useEffect(() => {
    onSettledRef.current = onSettled;
  }, [onSettled]);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(
    () => () => {
      for (const id of timeoutsRef.current) window.clearTimeout(id);
    },
    [],
  );

  const handleParked = useCallback(() => {
    if (settleStartedRef.current) return;
    settleStartedRef.current = true;
    setLineUp(true);
    const schedule = (ms: number, fn: () => void) => {
      timeoutsRef.current.push(window.setTimeout(fn, ms));
    };
    schedule(SETTLE.HIDE_GRID, () => setGridHidden(true));
    schedule(SETTLE.SOLID, () => setSolid(true));
    schedule(SETTLE.POP, () => setPop(true));
    schedule(SETTLE.PLACEHOLDER, () => setPlaceholderTyping(true));
    schedule(SETTLE.SEND, () => setSendBuilding(true));
    schedule(SETTLE.WELCOME, () => setWelcomeTyping(true));
    schedule(SETTLE.CHIPS, () => {
      setChipsVisible(true);
      setChipsTyping(true);
    });
    schedule(SETTLE.BODY, () => setBodyTyping(true));
    schedule(SETTLE.DONE, () => onSettledRef.current?.());
  }, []);

  useEffect(() => {
    if (reduced) return;
    const wrap = wrapRef.current;
    const grid = gridRef.current;
    if (!wrap || !grid) return;
    const engine = createBorderEngine({ wrap, svg: grid, onParked: handleParked });
    engineRef.current = engine;
    engine.start();
    // Type from mount, not from ready: gating the sequence on ready let the
    // host crossfade (ChatEmbedShell, keyed on embedReady) hide the typed
    // welcome + examples before they played -- datatap types during the load.
    // handleParked is idempotent, so the ready-time finish() -> onParked call
    // below stays a no-op.
    handleParked();
    const observer = new ResizeObserver(() => engine.rebuild());
    observer.observe(wrap);
    return () => {
      observer.disconnect();
      engine.destroy();
      engineRef.current = null;
    };
  }, [handleParked, reduced]);

  useEffect(() => {
    if (!ready) return;
    if (reduced) {
      onSettledRef.current?.();
      return;
    }
    engineRef.current?.finish();
  }, [ready, reduced]);

  const instant = reduced;

  return (
    <div
      className={className ? `dboot ${className}` : "dboot"}
      data-attach={showAttachment ? "1" : "0"}
      style={accent ? ({ "--dboot-caret": accent } as CSSProperties) : undefined}
    >
      <span className="dboot-sr" role="status">
        {label}
      </span>
      <div className="dboot-dock" aria-hidden="true">
        <div className="dboot-welcome">
          <TypedText text={welcome} active={welcomeTyping} speedMs={TYPE.WELCOME} instant={instant} />
        </div>
        <div className="dboot-body">
          <TypedText text={welcomeBody} active={bodyTyping} speedMs={TYPE.BODY} instant={instant} />
        </div>
        <div className="dboot-chips" data-visible={chipsVisible || instant ? "true" : "false"}>
          {suggestions.map((suggestion) => (
            <div className="dboot-chip" key={suggestion}>
              <span className="dboot-chip-mark">
                <Glyph cells={EXAMPLE_CELLS} className="dboot-glyph" />
              </span>
              <span className="dboot-chip-text">
                <TypedText text={suggestion} active={chipsTyping} speedMs={TYPE.CHIP} instant={instant} />
              </span>
            </div>
          ))}
        </div>
        <div className="dboot-composer-wrap" ref={wrapRef}>
          <div className="dboot-composer" data-solid={solid || instant ? "true" : "false"}>
            <span className="dboot-placeholder">
              <TypedText
                text={placeholder}
                active={placeholderTyping}
                speedMs={TYPE.PLACEHOLDER}
                instant={instant}
              />
            </span>
            <span className="dboot-send">
              <BuildingGlyph
                cells={SEND_CELLS}
                active={sendBuilding}
                speedMs={TYPE.SEND_BUILD}
                instant={instant}
                className="dboot-glyph"
              />
            </span>
          </div>
          {instant ? null : (
            <svg
              ref={gridRef}
              className="dboot-grid"
              data-hidden={gridHidden ? "true" : "false"}
              aria-hidden="true"
            />
          )}
          <span
            className="dboot-line"
            data-visible={lineUp ? "true" : "false"}
            data-solid={solid || instant ? "true" : "false"}
          />
          {showAttachment ? (
            <span className="dboot-plus" data-pop={pop || instant ? "true" : "false"}>
              <Glyph cells={PLUS_CELLS} className="dboot-glyph" />
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
