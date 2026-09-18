"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { DotMatrix } from "./DotMatrix";
import { signalDigichatReady } from "./boot-signal";

/**
 * Boot-lab variants: short local loaders used to iterate on the universal
 * boot animation. `?boot=<variant>` selects one at runtime; the server can
 * also thread it so first paint never shows the classic loader (the outline
 * bleed the classic pass caused).
 *
 * `toolchain` is the skin-proof one: it renders simulated tool calls with the
 * chat's own DotMatrix states (running spinner -> green check) and the same
 * row anatomy as the message tool calls, so whatever skin dresses the chat
 * dresses the boot too.
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
  | "toolchain";

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
};

/** Variants whose label types itself in (the terminal DNA). */
const TYPED: ReadonlySet<BootLabVariant> = new Set([
  "terminal",
  "waking",
  "booting",
]);

const TYPE_MS = 46;
const SETTLE_HOLD_MS = 180;

/** Simulated container/agent commands; one row each, in order. */
const TOOL_CHAIN: readonly string[] = [
  "pull digichat image",
  "mount deployment configuration",
  "warm up chat runtime",
  "verify foundry connection",
];

const CHAIN_STEP_MS = 560;

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
function ToolChainRow({ label, done }: { label: string; done: boolean }) {
  const liveMs = useLiveMs(!done);
  const ms = done ? CHAIN_STEP_MS : liveMs;
  return (
    <div
      className="aui-tool-fallback-trigger group/trigger text-muted-foreground flex w-full items-center gap-2 py-1.5 text-sm"
      data-slot="tool-fallback-trigger"
    >
      <DotMatrix
        state={done ? "success" : "tool"}
        label={done ? "Ok" : "Running"}
        className="aui-tool-fallback-trigger-icon size-3.5 shrink-0"
      />
      <span
        className="aui-tool-fallback-trigger-label-wrapper min-w-0 flex-1 truncate text-start leading-none"
        data-slot="tool-fallback-trigger-label"
      >
        {label}
      </span>
      <span className="aui-tool-fallback-duration text-muted-foreground text-xs tabular-nums">
        {(ms / 1000).toFixed(1)}s
      </span>
    </div>
  );
}

function ToolChain({
  instant,
  onDone,
}: {
  instant: boolean;
  onDone: () => void;
}) {
  const [step, setStep] = useState(instant ? TOOL_CHAIN.length : 0);
  useEffect(() => {
    if (instant) {
      setStep(TOOL_CHAIN.length);
      return;
    }
    if (step >= TOOL_CHAIN.length) return;
    const timer = setTimeout(() => setStep((current) => current + 1), CHAIN_STEP_MS);
    return () => clearTimeout(timer);
  }, [step, instant]);
  useEffect(() => {
    if (step >= TOOL_CHAIN.length) onDone();
  }, [step, onDone]);
  const visible = Math.min(step + 1, TOOL_CHAIN.length);
  return (
    <span className="dboot-lab-tools">
      {TOOL_CHAIN.slice(0, visible).map((label, index) => (
        <ToolChainRow key={label} label={label} done={index < step} />
      ))}
    </span>
  );
}

export function BootLabOverlay({
  variant,
  ready,
  onSettled,
  accent,
}: {
  variant: BootLabVariant;
  ready: boolean;
  onSettled: () => void;
  accent?: string;
}) {
  const reduced = useReducedMotion();
  const [chainDone, setChainDone] = useState(variant !== "toolchain");
  // The tool chain runs to completion before the chat pops up.
  const active = variant === "toolchain" ? ready && chainDone : ready;
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
      {variant === "toolchain" ? (
        <ToolChain instant={reduced} onDone={() => setChainDone(true)} />
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
