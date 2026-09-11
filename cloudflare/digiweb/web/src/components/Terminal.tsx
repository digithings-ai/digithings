"use client";
/** Typed terminal playback — the hero signature. Renders line-by-line with a
 *  blinking cursor; instant under reduced-motion. Content is component-authored. */
import { useEffect, useRef, useState } from "react";
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
    case "ok": return <span className="tl-ok"><b>{l.name.padEnd(12)}</b>{l.text}</span>;
    case "mod": return <span className="tl-mod"><b>{l.name.padEnd(13)}</b>{l.text}  →</span>;
  }
}

export function Terminal({ title, lines }: { title: string; lines: TermLine[] }) {
  const safe = useMotionSafe();
  const [n, setN] = useState(safe ? 0 : lines.length);
  const started = useRef(false);

  useEffect(() => {
    // useMotionSafe resolves after mount (hydration-safe): reduced-motion
    // users reach here with safe=false on the second pass — show everything
    // instantly, even if the pre-resolution pass already "started" (its timer
    // was cleaned up before ever ticking).
    if (!safe) {
      setN(lines.length);
      return;
    }
    if (started.current) return;
    started.current = true;
    let i = 0;
    const tick = () => {
      i += 1;
      setN(i);
      if (i < lines.length) {
        const prev = lines[i - 1];
        setTimeout(tick, prev.kind === "gap" ? 90 : prev.kind === "cmd" ? 420 : 200);
      }
    };
    const t = setTimeout(tick, 420);
    return () => clearTimeout(t);
  }, [safe, lines]);

  return (
    <div className="term">
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
