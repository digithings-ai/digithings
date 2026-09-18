"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { DotMatrix } from "./DotMatrix";
import { signalDigichatReady } from "./boot-signal";

/**
 * Boot-lab variants: short local loaders used to iterate on the universal
 * boot animation. `?boot=<variant>` selects one at runtime; the server can
 * also thread it so first paint never shows the classic loader (the outline
 * bleed the classic pass caused).
 */
export type BootLabVariant =
  | "terminal"
  | "waking"
  | "booting"
  | "spinner"
  | "spinneronly"
  | "typespin"
  | "dots"
  | "bar"
  | "bootlog"
  | "scramble"
  | "caret";

const VARIANTS: readonly BootLabVariant[] = [
  "terminal",
  "waking",
  "booting",
  "spinner",
  "spinneronly",
  "typespin",
  "dots",
  "bar",
  "bootlog",
  "scramble",
  "caret",
];

/** Copy per variant; null = nothing but the mark itself. */
const LABELS: Record<BootLabVariant, string | null> = {
  terminal: "loading",
  waking: "waking up…",
  booting: "booting up…",
  spinner: "loading",
  spinneronly: null,
  typespin: "loading",
  dots: "loading",
  bar: "loading",
  bootlog: "digichat --boot",
  scramble: "loading",
  caret: null,
};

/** Variants whose label types itself in (the terminal DNA). */
const TYPED: ReadonlySet<BootLabVariant> = new Set([
  "terminal",
  "waking",
  "booting",
]);

const TYPE_MS = 46;
const SETTLE_HOLD_MS = 180;

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

const BAR_CELLS = 10;

function BarLine() {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const interval = setInterval(
      () => setProgress((c) => (c + 1) % (BAR_CELLS + 2)),
      120,
    );
    return () => clearInterval(interval);
  }, []);
  const filled = Math.min(progress, BAR_CELLS);
  return (
    <span className="dboot-lab-line">
      <span>
        loading <span className="dboot-lab-muted">[</span>
        <span className="dboot-lab-accent">{"█".repeat(filled)}</span>
        <span className="dboot-lab-muted">{"░".repeat(BAR_CELLS - filled)}</span>
        <span className="dboot-lab-muted">]</span>
      </span>
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
  useSettle(ready, onSettled);
  const label = LABELS[variant];
  const caret =
    variant === "caret" ? (
      <span className="dboot-lab-caret" aria-hidden="true" />
    ) : null;
  return (
    <div
      className="dboot-lab"
      data-digichat-boot=""
      data-variant={variant}
      role="status"
      style={accent ? ({ "--dboot-caret": accent } as CSSProperties) : undefined}
    >
      {caret}
      {variant === "spinner" ? <SpinnerLine label={label} /> : null}
      {variant === "spinneronly" ? <SpinnerLine /> : null}
      {variant === "dots" ? <DotsLine /> : null}
      {variant === "bar" ? <BarLine /> : null}
      {variant === "bootlog" ? <BootLog /> : null}
      {variant === "scramble" && label ? (
        <ScrambleLine text={label} instant={reduced} />
      ) : null}
      {variant === "typespin" ? (
        <span className="dboot-lab-line dboot-lab-spin">
          <DotMatrix state="loading" className="size-3.5" />
          {label ? (
            <span>
              <TypedLabel text={label} instant={reduced} />
            </span>
          ) : null}
          <span className="dboot-lab-caret" aria-hidden="true" />
        </span>
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
