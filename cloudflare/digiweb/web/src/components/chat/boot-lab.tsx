"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { DotMatrix } from "./DotMatrix";
import {
  DIGI_CHAT_BOOT_STEP_EVENT,
  DIGI_CHAT_READY_EVENT,
  digichatBootClockMs,
  digichatBootSteps,
  hasDigichatReady,
  signalDigichatReady,
} from "./boot-signal";

/**
 * Boot-lab variants: short local loaders used to iterate on the universal
 * boot animation. `?boot=<variant>` selects one at runtime; the server can
 * also thread it so first paint never shows the classic loader (the outline
 * bleed the classic pass caused).
 *
 * The tool-chain family (`toolchain`, `tooltask`, `toolreason`, `toolfull`)
 * is the skin-proof one: simulated tool calls drawn with the chat's own
 * DotMatrix states and row anatomy (`aui-tool-fallback-trigger`,
 * `tool-group-trigger`, `reasoning-trigger`), so whatever skin dresses the
 * chat dresses the boot too. After the simulated commands finish a
 * `connect to digichat` row keeps ticking until the app's real ready signal
 * lands, which keeps 30-60s cold starts honest; `?bootdelay=<seconds>`
 * emulates a slow container locally.
 */
export type BootLabVariant =
  | "terminal"
  | "waking"
  | "booting"
  | "spinner"
  | "spinneronly"
  | "dots"
  | "bootlog"
  | "scramble"
  | "toolchain"
  | "tooltask"
  | "toolreason"
  | "toolfull";

const VARIANTS: readonly BootLabVariant[] = [
  "terminal",
  "waking",
  "booting",
  "spinner",
  "spinneronly",
  "dots",
  "bootlog",
  "scramble",
  "toolchain",
  "tooltask",
  "toolreason",
  "toolfull",
];

/** Copy per variant; null = the variant draws its own rows. */
const LABELS: Record<BootLabVariant, string | null> = {
  terminal: "loading",
  waking: "waking up…",
  booting: "booting up…",
  spinner: "loading",
  spinneronly: null,
  dots: "loading",
  bootlog: "digichat --boot",
  scramble: "loading",
  toolchain: null,
  tooltask: null,
  toolreason: null,
  toolfull: null,
};

/** Variants whose label types itself in (the terminal DNA). */
const TYPED: ReadonlySet<BootLabVariant> = new Set([
  "terminal",
  "waking",
  "booting",
]);

const TYPE_MS = 46;
const SETTLE_HOLD_MS = 180;

/** Facts the deployment actually reports; rows without facts stay detail-less. */
export type BootFacts = {
  starters?: number;
  model?: string;
  models?: number;
  toolLabels?: readonly string[];
  mcpServers?: number;
  backend?: string;
};

/** Real milestones the app reports while the container comes up. */
type BootMilestone = "image" | "config" | "runtime" | "loop" | "backend";

/**
 * Container/agent commands; one row each, in order. Rows adapt to the facts
 * the deployment actually reports (and only those) - extra rows appear when
 * the deployment carries tools or MCP servers, so different deployments show
 * different steps and numbers. Never invent counts. Each row carries the real
 * milestone that completes it (`ms` is the beat it keeps before that milestone
 * lands, and the cap when no signal ever does).
 */
export function toolChainRows(
  facts?: BootFacts,
): readonly {
  label: string;
  detail?: string;
  milestone: BootMilestone;
  ms: number;
}[] {
  const rows: {
    label: string;
    detail?: string;
    milestone: BootMilestone;
    ms: number;
  }[] = [
    { label: "pull digichat image", milestone: "image", ms: 1320 },
    {
      label: "mount deployment configuration",
      milestone: "config",
      ms: 640,
      detail: facts?.starters ? `${facts.starters} starters` : undefined,
    },
    {
      label: "warm up chat runtime",
      milestone: "runtime",
      ms: 880,
      detail: facts?.model
        ? facts.model
        : facts?.models
          ? `${facts.models} models`
          : undefined,
    },
  ];
  if (facts?.toolLabels?.length) {
    rows.push({
      label: "wire in the tools",
      milestone: "loop",
      ms: 760,
      detail: facts.toolLabels.join(", "),
    });
  }
  if (facts?.mcpServers) {
    rows.push({
      label: "attach mcp servers",
      milestone: "loop",
      ms: 720,
      detail: `${facts.mcpServers} servers`,
    });
  }
  rows.push({
    label: "wire in the backend",
    milestone: "backend",
    ms: 1402,
    detail: facts?.backend ? `${facts.backend} backend` : undefined,
  });
  return rows;
}

/** The tool-chain family shares the long-load behaviour below. */
const TOOLCHAIN_VARIANTS: ReadonlySet<BootLabVariant> = new Set([
  "toolchain",
  "tooltask",
  "toolreason",
  "toolfull",
]);

const TASK_LABEL = "Loading DigiChat";
const REASONING_LABEL = "waking up the container";
const HOLD_HINT = "cold start — this can take up to a minute";
/** Waiting this long surfaces the cold-start hint. */
const HOLD_HINT_MS = 10_000;
/** Still running this long: suggest a retry without declaring failure. */
const RETRY_HINT_MS = 45_000;
const RETRY_HINT = "taking longer than usual — ";
/** The hold row failed: the app never signalled ready (or said it failed). */
const FAIL_TEXT = "couldn't reach the chat — ";
const RETRY_LABEL = "retry";
/** Readiness cap: embedded surfaces wait for the app handshake; standalone
 *  surfaces never send one, so they settle on their own sooner. Embedded
 *  surfaces that pass the cap surface a failure + retry instead of settling. */
const EMBEDDED_CAP_MS = 120_000;
const STANDALONE_CAP_MS = 3_000;
/** Same-window failure signal: the app may dispatch it when the boot dies.
 *  The embed does not emit it yet; `?bootfail=<seconds>` demos it locally. */
const BOOT_FAILED_EVENT = "digichat:boot-failed";

/**
 * Resolve the lab variant: an explicit value (threaded from the embed server)
 * wins; otherwise fall back to `?boot=` on the URL; otherwise null (classic).
 */
export function resolveBootLabVariant(
  explicit?: string | null,
): BootLabVariant | null {
  const value =
    explicit != null
      ? explicit
      : typeof window === "undefined"
        ? null
        : new URL(window.location.href).searchParams.get("boot");
  return value != null && (VARIANTS as readonly string[]).includes(value)
    ? (value as BootLabVariant)
    : null;
}

/** `?bootdelay=<seconds>`: emulate a slow container locally (lab only). */
function resolveBootDelayMs(): number {
  if (typeof window === "undefined") return 0;
  const raw = new URL(window.location.href).searchParams.get("bootdelay");
  const seconds = raw == null ? 0 : Number(raw);
  return Number.isFinite(seconds) && seconds > 0
    ? Math.min(seconds, 300) * 1000
    : 0;
}

/** `?bootfail=<seconds>`: force the boot into its failed state (lab only). */
function resolveBootFailMs(): number {
  if (typeof window === "undefined") return 0;
  const raw = new URL(window.location.href).searchParams.get("bootfail");
  const seconds = raw == null ? 0 : Number(raw);
  return Number.isFinite(seconds) && seconds > 0
    ? Math.min(seconds, 300) * 1000
    : 0;
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

function useSettle(ready: boolean, onSettled: () => void) {
  const settledRef = useRef(false);
  useEffect(() => {
    if (!ready || settledRef.current) return;
    settledRef.current = true;
    const timer = setTimeout(() => {
      signalDigichatReady();
      onSettled();
    }, SETTLE_HOLD_MS);
    return () => clearTimeout(timer);
  }, [ready, onSettled]);
}

/**
 * The app's real ready signal: the embed dispatches it once the runtime is
 * up. Standalone surfaces never send one, so they fall back to a short cap.
 */
function useAppReady(enabled: boolean): { ready: boolean; timedOut: boolean } {
  const [ready, setReady] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    if (hasDigichatReady()) {
      setReady(true);
      return;
    }
    const onReady = () => setReady(true);
    window.addEventListener(DIGI_CHAT_READY_EVENT, onReady, { once: true });
    const standalone = window.parent === window;
    // Standalone surfaces never receive the handshake, so they settle on
    // their own; embedded surfaces that time out surface a failure + retry.
    const cap = setTimeout(() => {
      if (standalone) setReady(true);
      else setTimedOut(true);
    }, standalone ? STANDALONE_CAP_MS : EMBEDDED_CAP_MS);
    return () => {
      window.removeEventListener(DIGI_CHAT_READY_EVENT, onReady);
      clearTimeout(cap);
    };
  }, [enabled]);
  return { ready, timedOut };
}

/** The boot failed: the app dispatched `digichat:boot-failed` (or the lab
 *  knob forced it); `failAfterMs` also demos the state locally. */
function useAppFailure(enabled: boolean, failAfterMs: number): boolean {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    const onFailed = () => setFailed(true);
    window.addEventListener(BOOT_FAILED_EVENT, onFailed);
    const timer =
      failAfterMs > 0 ? setTimeout(onFailed, failAfterMs) : undefined;
    return () => {
      window.removeEventListener(BOOT_FAILED_EVENT, onFailed);
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [enabled, failAfterMs]);
  return failed;
}

/** Hold `value` back by `delayMs` after it flips true (the lab knob). */
function useDelayedTrue(value: boolean, delayMs: number): boolean {
  const [delayed, setDelayed] = useState(false);
  useEffect(() => {
    if (!value) {
      setDelayed(false);
      return;
    }
    if (delayMs === 0) {
      setDelayed(true);
      return;
    }
    const timer = setTimeout(() => setDelayed(true), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return delayed;
}

function TypedLabel({ text, instant }: { text: string; instant: boolean }) {
  const [count, setCount] = useState(instant ? text.length : 0);
  useEffect(() => {
    if (instant) {
      setCount(text.length);
      return;
    }
    const interval = setInterval(() => {
      setCount((current) => {
        if (current >= text.length) {
          clearInterval(interval);
          return current;
        }
        return current + 1;
      });
    }, TYPE_MS);
    return () => clearInterval(interval);
  }, [text, instant]);
  return <>{text.slice(0, count)}</>;
}

function SpinnerLine({ label }: { label?: string | null }) {
  return (
    <span className="dboot-lab-line dboot-lab-spin">
      <DotMatrix state="loading" className="size-3.5" />
      {label ? <span>{label}</span> : null}
    </span>
  );
}

function DotsLine() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setCount((c) => (c + 1) % 4), 420);
    return () => clearInterval(interval);
  }, []);
  return (
    <span className="dboot-lab-line">
      loading<span className="dboot-lab-dots" aria-hidden="true">{".".repeat(count)}</span>
    </span>
  );
}

function BootLog() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timers = [
      setTimeout(() => setStep(1), 620),
      setTimeout(() => setStep(2), 1240),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);
  return (
    <span className="dboot-lab-lines">
      <span className="dboot-lab-line">$ digichat --boot</span>
      {step > 0 ? (
        <span className="dboot-lab-line dboot-lab-muted">ok</span>
      ) : null}
    </span>
  );
}

const SCRAMBLE_GLYPHS = "▚▞█▓▒░<>/\\|=+*";

function ScrambleLine({ text, instant }: { text: string; instant: boolean }) {
  const [display, setDisplay] = useState(instant ? text : "");
  useEffect(() => {
    if (instant) {
      setDisplay(text);
      return;
    }
    let frame = 0;
    const total = text.length * 2;
    const interval = setInterval(() => {
      frame += 1;
      const reveal = Math.floor((frame / total) * text.length);
      setDisplay(
        text.slice(0, reveal) +
          Array.from(
            { length: text.length - reveal },
            (_, index) =>
              SCRAMBLE_GLYPHS[(frame + index) % SCRAMBLE_GLYPHS.length],
          ).join(""),
      );
      if (frame >= total) {
        clearInterval(interval);
        setDisplay(text);
      }
    }, 40);
    return () => clearInterval(interval);
  }, [text, instant]);
  return <span className="dboot-lab-line">{display}</span>;
}

/** Live elapsed ms while `active` (the running tool duration the chat shows). */
function useLiveMs(active: boolean): number {
  const [ms, setMs] = useState(0);
  useEffect(() => {
    if (!active) return;
    const started = Date.now();
    const interval = setInterval(() => setMs(Date.now() - started), 120);
    return () => clearInterval(interval);
  }, [active]);
  return ms;
}

/**
 * One simulated tool call: the same row anatomy as the message tool calls
 * (`aui-tool-fallback-trigger` + DotMatrix states), so any skin styles it.
 */
function ToolChainRow({
  label,
  detail,
  durationMs,
  done,
  failed = false,
}: {
  label: string;
  detail?: string;
  durationMs: number;
  done: boolean;
  failed?: boolean;
}) {
  const liveMs = useLiveMs(!done && !failed);
  const ms = done ? durationMs : liveMs;
  return (
    <div
      className="aui-tool-fallback-trigger group/trigger text-muted-foreground flex w-full items-center gap-2 py-1.5 text-sm"
      data-slot="tool-fallback-trigger"
    >
      <DotMatrix
        state={failed ? "error" : done ? "success" : "tool"}
        label={failed ? "Error" : done ? "Ok" : "Running"}
        className="aui-tool-fallback-trigger-icon size-3.5 shrink-0"
      />
      <span
        className="aui-tool-fallback-trigger-label-wrapper min-w-0 flex-1 truncate text-start leading-none"
        data-slot="tool-fallback-trigger-label"
      >
        {label}
        {detail ? <span className="ml-1 opacity-60">· {detail}</span> : null}
      </span>
      <span className="aui-tool-fallback-duration text-muted-foreground text-xs tabular-nums">
        {(ms / 1000).toFixed(1)}s
      </span>
    </div>
  );
}

/** The chain's task header (the tool-group trigger anatomy). */
function TaskHeaderRow({ done, failed }: { done: boolean; failed: boolean }) {
  return (
    <div
      className="text-muted-foreground flex w-full items-center gap-2 py-1.5 text-sm"
      data-slot="tool-group-trigger"
    >
      <span
        className="inline-flex size-3.5 shrink-0 items-center justify-center"
        data-slot="tool-group-trigger-loader"
      >
        <DotMatrix
          state={failed ? "error" : done ? "success" : "loading"}
          label={failed ? "Error" : done ? "Ok" : "Loading"}
          className="size-3.5"
        />
      </span>
      <span
        className={
          "min-w-0 flex-1 truncate text-start text-xs leading-none font-medium" +
          (done || failed ? "" : " shimmer motion-reduce:animate-none")
        }
        data-slot="tool-group-trigger-label"
      >
        {TASK_LABEL}
      </span>
      <span data-slot="tool-group-trigger-chevron">
        <DotMatrix
          state="expand"
          label="Toggle tools"
          className="size-3.5 -rotate-90"
        />
      </span>
    </div>
  );
}

/** A reasoning row above the calls (the reasoning trigger anatomy). */
function ReasoningRow({
  active,
  durationMs,
}: {
  active: boolean;
  durationMs: number;
}) {
  return (
    <div
      className="aui-reasoning-trigger group/trigger text-muted-foreground flex w-full items-center gap-2 py-1.5 text-sm"
      data-slot="reasoning-trigger"
    >
      <span
        className="aui-reasoning-trigger-icon inline-flex size-3.5 shrink-0 items-center justify-center"
        data-slot="reasoning-trigger-icon"
      >
        <DotMatrix
          state={active ? "thinking" : "thought"}
          label={active ? "Reasoning" : "Thought"}
          className="size-3.5"
        />
      </span>
      <span
        className={
          "aui-reasoning-trigger-label-wrapper min-w-0 flex-1 truncate text-start leading-none tabular-nums" +
          (active ? " shimmer motion-reduce:animate-none" : "")
        }
        data-slot="reasoning-trigger-label"
      >
        {REASONING_LABEL}
        {active ? "" : ` (${(durationMs / 1000).toFixed(1)}s)`}
      </span>
      <span data-slot="reasoning-trigger-chevron">
        <DotMatrix
          state="expand"
          label="Toggle reasoning"
          className="size-3.5"
        />
      </span>
    </div>
  );
}

/** Reload is the retry: it re-runs the boot handshake from scratch. */
function RetryButton() {
  return (
    <button
      type="button"
      className="dboot-lab-retry"
      onClick={() => window.location.reload()}
    >
      {RETRY_LABEL}
    </button>
  );
}

/** The reassurance ladder: cold-start hint -> retry suggestion -> failed. */
function HoldStatus({ failed }: { failed: boolean }) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    if (failed) return;
    const cold = setTimeout(() => setStage(1), HOLD_HINT_MS);
    const retry = setTimeout(() => setStage(2), RETRY_HINT_MS);
    return () => {
      clearTimeout(cold);
      clearTimeout(retry);
    };
  }, [failed]);
  if (failed) {
    return (
      <span className="dboot-lab-line dboot-lab-hint">
        {FAIL_TEXT}
        <RetryButton />
      </span>
    );
  }
  if (stage >= 2) {
    return (
      <span className="dboot-lab-line dboot-lab-hint">
        {RETRY_HINT}
        <RetryButton />
      </span>
    );
  }
  if (stage === 1) {
    return <span className="dboot-lab-line dboot-lab-hint">{HOLD_HINT}</span>;
  }
  return null;
}

function useBootSteps(): ReadonlySet<string> {
  const [steps, setSteps] = useState<ReadonlySet<string>>(
    () => new Set(digichatBootSteps()),
  );
  useEffect(() => {
    const onStep = () => setSteps(new Set(digichatBootSteps()));
    window.addEventListener(DIGI_CHAT_BOOT_STEP_EVENT, onStep);
    return () => window.removeEventListener(DIGI_CHAT_BOOT_STEP_EVENT, onStep);
  }, []);
  return steps;
}

function ToolChain({
  instant,
  ready,
  failed,
  showTask,
  showReasoning,
  facts,
  onDone,
}: {
  instant: boolean;
  ready: boolean;
  failed: boolean;
  showTask: boolean;
  showReasoning: boolean;
  facts?: BootFacts;
  onDone: () => void;
}) {
  const rows = useMemo(() => toolChainRows(facts), [facts]);
  const steps = useBootSteps();
  const mountClock = useRef(digichatBootClockMs());
  const [doneAt, setDoneAt] = useState<(number | null)[]>(() =>
    rows.map(() => (instant ? mountClock.current : null)),
  );
  const [tick, setTick] = useState(0);
  const pending = doneAt.some((value) => value === null);
  const firstPending = doneAt.findIndex((value) => value === null);
  const chainDone = !pending;
  // Poll while rows are open: each row flips when its real milestone lands.
  // Image rows and tool/MCP rows keep a short beat so the chain stays
  // readable, config/runtime fall back to a cap so a missed signal cannot
  // wedge the boot, and the backend row waits for the app's real ready edge.
  useEffect(() => {
    if (instant || !pending) return;
    const interval = setInterval(() => setTick((value) => value + 1), 250);
    return () => clearInterval(interval);
  }, [instant, pending]);
  useEffect(() => {
    if (instant || !pending) return;
    setDoneAt((current) => {
      const index = current.findIndex((value) => value === null);
      if (index === -1) return current;
      const row = rows[index];
      if (row === undefined) return current;
      const previousDone = index === 0 ? mountClock.current : current[index - 1];
      if (previousDone === null || previousDone === undefined) return current;
      const now = digichatBootClockMs();
      const reached =
        row.milestone === "backend"
          ? ready
          : row.milestone === "config" || row.milestone === "runtime"
            ? steps.has(row.milestone) || now - previousDone >= row.ms * 2
            : now - previousDone >= row.ms;
      if (!reached) return current;
      const next = [...current];
      next[index] = now;
      return next;
    });
  }, [tick, instant, pending, ready, rows, steps]);
  useEffect(() => {
    if (chainDone) onDone();
  }, [chainDone, onDone]);
  const visible = firstPending === -1 ? rows.length : firstPending + 1;
  // The last row waits on the real ready edge - that is the honest "connect"
  // beat, and the hold/retry ladder attaches to it.
  const waiting = !failed && !ready && firstPending === rows.length - 1;
  const completedMs =
    chainDone && doneAt[rows.length - 1] != null
      ? doneAt[rows.length - 1]! - mountClock.current
      : 0;
  return (
    <span className="dboot-lab-tools">
      {showTask ? (
        <TaskHeaderRow done={chainDone && ready} failed={failed} />
      ) : null}
      {showReasoning ? (
        <ReasoningRow active={!chainDone && !failed} durationMs={completedMs} />
      ) : null}
      {rows.slice(0, visible).map((row, index) => {
        const done = doneAt[index] != null;
        const start =
          index === 0
            ? mountClock.current
            : doneAt[index - 1] ?? mountClock.current;
        return (
          <ToolChainRow
            key={row.label}
            label={row.label}
            detail={row.detail}
            durationMs={done ? doneAt[index]! - start : 0}
            done={done}
            failed={
              failed &&
              index === (firstPending === -1 ? rows.length - 1 : firstPending)
            }
          />
        );
      })}
      {waiting || failed ? <HoldStatus failed={failed} /> : null}
    </span>
  );
}

export function BootLabOverlay({
  variant,
  ready,
  onSettled,
  accent,
  facts,
}: {
  variant: BootLabVariant;
  ready: boolean;
  onSettled: () => void;
  accent?: string;
  facts?: BootFacts;
}) {
  const reduced = useReducedMotion();
  const isToolchain = TOOLCHAIN_VARIANTS.has(variant);
  const [chainDone, setChainDone] = useState(!isToolchain);
  const [bootDelayMs] = useState(resolveBootDelayMs);
  const [failAfterMs] = useState(resolveBootFailMs);
  // `?bootfail` forces the failure demo: ignore the real ready signal so the
  // boot cannot settle before the forced failure lands.
  const app = useAppReady(isToolchain && failAfterMs === 0);
  const appReady = useDelayedTrue(app.ready, bootDelayMs);
  const appFailed = useAppFailure(isToolchain, failAfterMs);
  const failed = isToolchain && (appFailed || app.timedOut);
  // The tool chain runs to completion and then waits for the real ready
  // signal, so long cold starts keep a live row instead of looking done.
  // A failed boot never settles: the overlay keeps the error + retry up.
  const active = isToolchain ? ready && chainDone && appReady && !failed : ready;
  useSettle(active, onSettled);
  const label = LABELS[variant];
  return (
    <div
      className="dboot-lab"
      data-digichat-boot=""
      data-variant={variant}
      role="status"
      style={accent ? ({ "--dboot-caret": accent } as CSSProperties) : undefined}
    >
      {variant === "spinner" ? <SpinnerLine label={label} /> : null}
      {variant === "spinneronly" ? <SpinnerLine /> : null}
      {variant === "dots" ? <DotsLine /> : null}
      {variant === "bootlog" ? <BootLog /> : null}
      {variant === "scramble" && label ? (
        <ScrambleLine text={label} instant={reduced} />
      ) : null}
      {isToolchain ? (
        <ToolChain
          instant={reduced}
          ready={appReady}
          failed={failed}
          showTask={variant === "tooltask" || variant === "toolfull"}
          showReasoning={variant === "toolreason" || variant === "toolfull"}
          facts={facts}
          onDone={() => setChainDone(true)}
        />
      ) : null}
      {TYPED.has(variant) && label ? (
        <span className="dboot-lab-line">
          <span>
            <TypedLabel text={label} instant={reduced} />
          </span>
          <span className="dboot-lab-caret" aria-hidden="true" />
        </span>
      ) : null}
    </div>
  );
}
