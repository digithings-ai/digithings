"use client";

import { useEffect, useReducer, useRef, type ReactNode } from "react";
import { m, useMotionSafe } from "../../motion/primitives";
import { cn } from "../../lib/utils";
import { ChatToolCall } from "./ChatToolCall";

/**
 * ChatPlayback — a props-driven, SCRIPTED chat simulation in a terminal frame.
 * The caller supplies an ordered script; the part types the user prompts, shows
 * tool-call rows (real names and args, supplied by the caller), and streams the
 * assistant text. It never talks to a model or a server and it invents nothing:
 * every word, tool name, argument and result comes from `script`, and a
 * REQUIRED `badge` prop is rendered inside the frame chrome so the surface
 * always says what it is ("Simulation · scripted · not connected to any MCP
 * server").
 *
 * Behaviour
 *  - starts once when the frame scrolls into view (IntersectionObserver), plays
 *    once, then offers `[replay]`; `[pause]` / `[play]` and `[skip]` are visible
 *    while it runs (it auto-runs well past 5s);
 *  - the only React state is the step index, the char count and a phase, advanced
 *    on a ~30ms timer while a text step types (no per-frame state, no rAF);
 *  - reduced motion, no JS, no IntersectionObserver and server render all show
 *    the FULL transcript, statically, with no controls;
 *  - a tool `result` is shown only once its (simulated) call has settled;
 *    `masked` blanks every non-space character to `▒` so a result can be shown
 *    as "a result came back" without claiming its content;
 *  - tool rows show no duration: a latency here would be invented.
 *
 * A11y: the animated transcript is `aria-hidden` + `inert` (its expand buttons
 * are decorative here) and the region is `aria-live="off"`; a plain-text
 * `sr-only` ordered list carries the full transcript once, statically. The
 * header, badge, status and controls sit outside the hidden region.
 *
 * Motion: row entrance is `m.div` (opacity + translateY only) under a
 * `MotionProvider`, gated by `useMotionSafe`; the static branch renders none.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/ui/styles/chat-widgets.css";   (ChatToolCall rail + running pulse)
 *                 @source "<path-to>/packages/ui/src/components/chat";
 * Chrome is utilities-only (no family sheet, no keyframes of its own).
 */
export type ChatPlaybackTable = { columns: string[]; rows: string[][] };

export type ChatPlaybackTool = {
  /** Real tool name, e.g. `digiquant.list_strategies`. */
  name: string;
  /** Argument summary, rendered `(args)` — supplied by the caller, real. */
  args?: string;
  /** What came back: text (newlines split lines), a list of lines, or a table. Omit for no body. */
  result?: string | string[] | ChatPlaybackTable;
  /** Blank every non-space character of `result` to `▒` (shows the shape, not the content). */
  masked?: boolean;
  /** How long the call shows as running before it settles. Default 700. */
  runMs?: number;
};

export type ChatPlaybackStep = {
  role: "user" | "assistant" | "tool";
  /** Prompt or reply text (user / assistant steps). */
  text?: string;
  /** The call (tool steps). */
  tool?: ChatPlaybackTool;
  /** Pause before this step starts, in ms. Defaults per role. */
  delayMs?: number;
};

export type ChatPlaybackProps = {
  /** The scripted steps, in order. Data, not a component. */
  script: ChatPlaybackStep[];
  /** REQUIRED honesty badge inside the frame, e.g. "Simulation · scripted · not connected to any MCP server". */
  badge: string;
  /** Caller-supplied title-row label, e.g. "local mcp session". */
  header: string;
  /** Accessible name for the region. Default: the header. */
  ariaLabel?: string;
  className?: string;
};

type Mode = "static" | "armed" | "playing" | "paused" | "done";
type Phase = "wait" | "work";
type State = { mode: Mode; step: number; chars: number; phase: Phase };
type Action =
  | { type: "static" }
  | { type: "arm" }
  | { type: "play" }
  | { type: "pause" }
  | { type: "skip" }
  | { type: "replay" }
  | { type: "advance"; len: number; total: number; rate: number; tool: boolean };

const TICK_MS = 30;
const USER_CPS = 1; // chars per tick
const ASSISTANT_CPS = 2;
const DEFAULT_DELAY: Record<ChatPlaybackStep["role"], number> = { user: 500, tool: 450, assistant: 350 };
const FULL: State = { mode: "static", step: 0, chars: 0, phase: "wait" };

function reduce(s: State, a: Action): State {
  switch (a.type) {
    case "static":
      return s.mode === "static" ? s : FULL;
    case "arm":
      return s.mode === "static" ? { mode: "armed", step: 0, chars: 0, phase: "wait" } : s;
    case "play":
      return s.mode === "armed" || s.mode === "paused" ? { ...s, mode: "playing" } : s;
    case "pause":
      return s.mode === "playing" ? { ...s, mode: "paused" } : s;
    case "skip":
      return s.mode === "playing" || s.mode === "paused" ? { ...s, mode: "done" } : s;
    case "replay":
      return s.mode === "done" ? { mode: "playing", step: 0, chars: 0, phase: "wait" } : s;
    case "advance": {
      if (s.mode !== "playing") return s;
      const next = (): State =>
        s.step + 1 >= a.total
          ? { ...s, mode: "done", step: a.total }
          : { ...s, step: s.step + 1, chars: 0, phase: "wait" };
      if (s.phase === "wait") return { ...s, phase: "work", chars: 0 };
      if (a.tool) return next();
      const chars = Math.min(a.len, s.chars + a.rate);
      return chars >= a.len ? next() : { ...s, chars };
    }
  }
}

const maskText = (t: string) => t.replace(/\S/g, "▒");

function resultLines(tool: ChatPlaybackTool): string[] {
  const r = tool.result;
  if (r === undefined || (typeof r === "object" && !Array.isArray(r))) return [];
  const lines = Array.isArray(r) ? r : r.split("\n");
  return tool.masked ? lines.map(maskText) : lines;
}

function resultTable(tool: ChatPlaybackTool): ChatPlaybackTable | null {
  const r = tool.result;
  if (r === undefined || typeof r === "string" || Array.isArray(r)) return null;
  return tool.masked
    ? { columns: r.columns, rows: r.rows.map((row) => row.map(maskText)) }
    : r;
}

function ResultBody({ tool }: { tool: ChatPlaybackTool }): ReactNode {
  const lines = resultLines(tool);
  const table = resultTable(tool);
  if (lines.length === 0 && !table) return null;
  return (
    <>
      {lines.map((l, i) => (
        <p key={i} className="my-[0.12rem] whitespace-pre-wrap break-words font-mono text-[0.74rem] leading-[1.5] text-term-mute">
          {l}
        </p>
      ))}
      {table ? (
        <div className="my-1 max-w-full overflow-x-auto">
          <table className="border-collapse font-mono text-[0.72rem] leading-[1.4]">
            <thead>
              <tr>
                {table.columns.map((c, i) => (
                  <th key={i} scope="col" className="border border-term-hair px-2 py-1 text-start font-normal text-term-ink">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci} className="whitespace-nowrap border border-term-hair px-2 py-1 text-term-mute">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}

function srLine(step: ChatPlaybackStep): string {
  if (step.role === "user") return `You: ${step.text ?? ""}`;
  if (step.role === "assistant") return `Assistant: ${step.text ?? ""}`;
  const t = step.tool;
  if (!t) return "Tool call";
  const call = `Tool call: ${t.name}${t.args ? `(${t.args})` : ""}.`;
  if (t.result === undefined) return call;
  if (t.masked) return `${call} The result is withheld in this simulation.`;
  const table = resultTable(t);
  if (table) {
    return `${call} Result table, columns ${table.columns.join(", ")}: ${table.rows.map((r) => r.join(" / ")).join("; ")}.`;
  }
  return `${call} Result: ${resultLines(t).join(" ")}`;
}

const CTL =
  "shrink-0 cursor-pointer bg-transparent p-0 font-[inherit] text-ink-mute transition-colors hover:text-ink focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent";

const STATUS_WORD: Record<Mode, string> = {
  static: "transcript",
  armed: "waiting for view",
  playing: "playing",
  paused: "paused",
  done: "done",
};

function Caret() {
  return (
    <span
      aria-hidden="true"
      className="ms-[0.15rem] inline-block h-[0.95em] w-[0.5ch] translate-y-[0.12em] bg-accent motion-safe:animate-pulse"
    />
  );
}

export function ChatPlayback({ script, badge, header, ariaLabel, className }: ChatPlaybackProps) {
  const safe = useMotionSafe();
  const [s, dispatch] = useReducer(reduce, FULL);
  const frameRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const total = script.length;

  // Arm (empty, wait for view) only when motion is allowed and IO exists;
  // otherwise — reduced motion, no IO, SSR — the full transcript stays.
  useEffect(() => {
    if (!safe || total === 0 || typeof IntersectionObserver === "undefined") {
      dispatch({ type: "static" });
      return;
    }
    dispatch({ type: "arm" });
  }, [safe, total]);

  useEffect(() => {
    if (s.mode !== "armed") return;
    const el = frameRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          dispatch({ type: "play" });
          io.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [s.mode]);

  // The one timer: a wait before the step, then ~30ms ticks while text types,
  // or a single settle delay for a tool call.
  useEffect(() => {
    if (s.mode !== "playing") return;
    const cur = script[s.step];
    if (!cur) return;
    const isTool = cur.role === "tool";
    const len = isTool ? 0 : (cur.text ?? "").length;
    const delay =
      s.phase === "wait"
        ? (cur.delayMs ?? DEFAULT_DELAY[cur.role])
        : isTool
          ? (cur.tool?.runMs ?? 700)
          : TICK_MS;
    const id = setTimeout(
      () =>
        dispatch({
          type: "advance",
          len,
          total,
          rate: cur.role === "user" ? USER_CPS : ASSISTANT_CPS,
          tool: isTool,
        }),
      delay,
    );
    return () => clearTimeout(id);
  }, [s, script, total]);

  // Follow the newest line inside the frame only (never scrolls the page).
  useEffect(() => {
    const el = scrollRef.current;
    if (el && (s.mode === "playing" || s.mode === "done")) el.scrollTop = el.scrollHeight;
  }, [s.mode, s.step, s.chars, s.phase]);

  const full = s.mode === "static" || s.mode === "done";
  const animated = s.mode !== "static";
  const progress = full ? 1 : total === 0 ? 0 : Math.min(1, s.step / total);

  const rows: ReactNode[] = [];
  script.forEach((step, i) => {
    const visible = full || i < s.step || (i === s.step && s.phase === "work" && s.mode !== "armed");
    if (!visible) return;
    const current = !full && i === s.step;
    const typing = current && step.role !== "tool";
    const text = step.text ?? "";
    const shown = current && typing ? text.slice(0, s.chars) : text;

    let body: ReactNode;
    if (step.role === "tool" && step.tool) {
      const settled = !current;
      const hasResult = settled && step.tool.result !== undefined;
      body = (
        <ChatToolCall
          name={step.tool.name}
          args={step.tool.args}
          status={settled ? "ok" : "running"}
          open={hasResult}
        >
          {hasResult ? <ResultBody tool={step.tool} /> : undefined}
        </ChatToolCall>
      );
    } else {
      const isUser = step.role === "user";
      body = (
        <p className="m-0 flex items-baseline gap-2 font-mono text-[0.78rem] leading-[1.65] text-term-ink">
          <span className="shrink-0 tracking-[0.04em] text-term-mute" aria-hidden="true">
            {isUser ? "[you]" : "[agent]"}
          </span>
          <span className="min-w-0 whitespace-pre-wrap break-words">
            {shown}
            {typing ? <Caret /> : null}
          </span>
        </p>
      );
    }

    rows.push(
      animated ? (
        <m.div
          key={i}
          className="py-[0.3rem]"
          data-motion=""
          initial={s.mode === "done" ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
        >
          {body}
        </m.div>
      ) : (
        <div key={i} className="py-[0.3rem]">
          {body}
        </div>
      ),
    );
  });

  const label = ariaLabel ?? header;

  return (
    <section
      ref={frameRef}
      role="region"
      aria-label={label}
      aria-live="off"
      data-slot="chat-playback"
      data-mode={s.mode}
      className={cn("min-w-0 border border-hair bg-surface font-mono", className)}
    >
      <div className="flex items-center gap-3 border-b border-hair px-3 py-2 text-[0.68rem] tracking-[0.04em] text-ink-mute">
        <span aria-hidden="true">[chat]</span>
        <span className="min-w-0 flex-1 truncate text-ink-soft">{header}</span>
        {s.mode === "playing" ? (
          <button type="button" className={CTL} onClick={() => dispatch({ type: "pause" })} aria-label="Pause playback">
            [pause]
          </button>
        ) : null}
        {s.mode === "paused" || s.mode === "armed" ? (
          <button type="button" className={CTL} onClick={() => dispatch({ type: "play" })} aria-label="Play the scripted session">
            [play]
          </button>
        ) : null}
        {s.mode === "playing" || s.mode === "paused" ? (
          <button type="button" className={CTL} onClick={() => dispatch({ type: "skip" })} aria-label="Skip to the full transcript">
            [skip]
          </button>
        ) : null}
        {s.mode === "done" ? (
          <button type="button" className={CTL} onClick={() => dispatch({ type: "replay" })} aria-label="Replay the scripted session">
            [replay]
          </button>
        ) : null}
      </div>

      <div className="flex items-center gap-3 border-b border-hair px-3 py-1.5 text-[0.66rem] text-ink-soft">
        <span className="min-w-0 flex-1" data-slot="chat-playback-badge">{`◇ ${badge}`}</span>
        <span className="shrink-0 text-ink-mute" aria-hidden="true">{`[${STATUS_WORD[s.mode]}]`}</span>
      </div>

      <div aria-hidden="true" className="relative h-px bg-hair">
        <div
          className="absolute inset-0 origin-left bg-ink-mute transition-transform duration-200 motion-reduce:transition-none"
          style={{ transform: `scaleX(${progress})` }}
        />
      </div>

      <div
        ref={scrollRef}
        className="h-[24rem] overflow-y-auto overscroll-contain bg-term-bg px-3 py-3 sm:h-[26rem] sm:px-4"
      >
        <div aria-hidden="true" inert>
          {rows}
          {s.mode === "done" ? (
            <p className="m-0 pt-2 text-[0.68rem] tracking-[0.04em] text-term-mute">
              {"── end of scripted session ──"}
            </p>
          ) : null}
        </div>
      </div>

      <ol className="sr-only" aria-label="Full transcript">
        {script.map((step, i) => (
          <li key={i}>{srLine(step)}</li>
        ))}
      </ol>
    </section>
  );
}
