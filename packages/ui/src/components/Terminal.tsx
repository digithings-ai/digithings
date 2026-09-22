"use client";
/** Typed terminal playback — the hero signature. Renders line-by-line with a
 *  blinking cursor; instant under reduced-motion. Content is component-authored. */
import { useEffect, useState } from "react";
import { useMotionSafe } from "../motion/primitives";

export type TermLine =
  | { kind: "cmd" | "out" | "install" | "arrow"; text: string }
  | { kind: "ok" | "mod"; name: string; text: string }
  | { kind: "gap" };

function Line({ l }: { l: TermLine }) {
  switch (l.kind) {
    case "gap": return <br />;
    case "cmd": return <span className="tl-cmd">{l.text}</span>;
    case "out": return <span className="tl-out">{l.text}</span>;
    case "install": return <span className="tl-install">{l.text}</span>;
    case "arrow": return <span className="tl-arrow">{l.text}</span>;
    case "ok": return <span className="tl-ok"><b>{l.name.padEnd(15)}</b>{l.text}</span>;
    case "mod": return <span className="tl-mod"><b>{l.name.padEnd(15)}</b>{l.text}  →</span>;
  }
}

export function Terminal({
  title,
  lines,
  size = "default",
  fill = false,
  className,
}: {
  title: string;
  lines: TermLine[];
  /** `compact` is the smaller register — tighter body type and window bar. */
  size?: "default" | "compact";
  /**
   * Stretch `.term` to its wrapper's height instead of sizing to the text, so
   * a scripted playback never grows the box as lines type in. Pair with a
   * fixed-height wrapper; the body clips rather than expanding.
   */
  fill?: boolean;
  className?: string;
}) {
  const safe = useMotionSafe();
  const [n, setN] = useState(safe ? 0 : lines.length);

  useEffect(() => {
    // useMotionSafe resolves after mount (hydration-safe): reduced-motion
    // users reach here with safe=false on the second pass — show everything
    // instantly.
    if (!safe) {
      setN(lines.length);
      return;
    }
    // The lead-in and the inter-line waits are chained timeouts, so the whole
    // chain is tracked and cleared together on cleanup. A first-render effect
    // pass is guaranteed (useMotionSafe flips `mounted` one tick after mount),
    // which re-runs this effect; every pending timer must be cancelled and the
    // chain restarted from zero, or the re-run would leave the body empty.
    let i = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      i += 1;
      setN(i);
      if (i < lines.length) {
        const prev = lines[i - 1];
        timer = setTimeout(tick, prev.kind === "gap" ? 90 : prev.kind === "cmd" ? 420 : 200);
      }
    };
    timer = setTimeout(tick, 420);
    return () => clearTimeout(timer);
  }, [safe, lines]);

  const root = ["term", size === "compact" ? "term--compact" : "", fill ? "term--fill" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={root}>
      <div className="term-bar"><i /><i /><i /><span className="term-title">{title}</span></div>
      <pre className="term-body">
        {lines.slice(0, n).map((l, k) => (
          <span key={k}>
            <Line l={l} />{l.kind !== "gap" ? "\n" : ""}
          </span>
        ))}
        {n >= lines.length && <span className="term-cursor" />}
      </pre>
    </div>
  );
}
