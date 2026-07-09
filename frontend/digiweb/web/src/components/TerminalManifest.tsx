"use client";
/**
 * Terminal manifest — the `cli ps` process pane behind digithings-web's
 * ModuleManifest (#1415): a prompt head line, selectable rows (status dot,
 * two-tone mono name, optional port, blurb), and an output panel where the
 * selected row's detail types out at a blinking cursor. Rows arrive as props;
 * selection is uncontrolled by default or controlled via `selectedId`.
 * Row-appear stagger and the type-out both degrade under reduced motion.
 * Pane surface, row states, keyframes, and the container-query column
 * collapse live in styles/terminal-manifest.css (import it once app-wide).
 * The pane deliberately wears the manifest chrome (prompt head line), not
 * the <Terminal> window bar — its frame is page CSS and its body is a
 * scripted playback; compose the two side by side when both are wanted.
 */
import { useEffect, useState, type ReactNode } from "react";
import { useMotionSafe } from "../motion/primitives";

export type TerminalManifestStatus = "online" | "roadmap";

export type TerminalManifestRow = {
  id: string;
  /** Lowercase process name; `namePrefix` splits it into ink + accent. */
  name: string;
  /** Optional port column — rendered only when at least one row carries one. */
  port?: string | number;
  status: TerminalManifestStatus;
  /** Row summary column; also the typed output when `detail` is absent. */
  blurb: string;
  /** Output typed at the cursor when the row is selected. */
  detail?: string;
};

export type TerminalManifestProps = {
  /** Head-line command, e.g. `digithings ps`. */
  command: string;
  rows: TerminalManifestRow[];
  /** Head-line prompt mark. */
  prompt?: string;
  /** Trailing head-line annotation, e.g. `· 7 online · 3 on the roadmap`. */
  meta?: string;
  /** Idle output line shown before any row is selected. */
  hint?: string;
  /** Two-tone name split: this leading fragment renders ink, the rest accent. */
  namePrefix?: string;
  /** Staggered row-appear animation (CSS keyframe; off under reduced motion). */
  animateRows?: boolean;
  /** Controlled selection; omit to let the pane own it. */
  selectedId?: string | null;
  defaultSelectedId?: string | null;
  onSelect?: (id: string | null) => void;
  /** Rendered under the output panel — e.g. a hand-off button. */
  footer?: ReactNode;
  className?: string;
  "aria-label"?: string;
};

function RowName({ name, prefix }: { name: string; prefix?: string }) {
  if (prefix && name.startsWith(prefix) && name.length > prefix.length) {
    return (
      <>
        <span className="text-ink">{prefix}</span>
        <span className="text-accent">{name.slice(prefix.length)}</span>
      </>
    );
  }
  return <span className="text-ink">{name}</span>;
}

export function TerminalManifest({
  command,
  rows,
  prompt = "$",
  meta,
  hint = "select a module",
  namePrefix,
  animateRows = true,
  selectedId,
  defaultSelectedId = null,
  onSelect,
  footer,
  className,
  "aria-label": ariaLabel,
}: TerminalManifestProps) {
  const safe = useMotionSafe();
  const [ownSel, setOwnSel] = useState<string | null>(defaultSelectedId);
  const sel = selectedId !== undefined ? selectedId : ownSel;
  const selRow = sel ? (rows.find((r) => r.id === sel) ?? null) : null;
  const out = selRow ? (selRow.detail ?? selRow.blurb) : "";
  const open = selRow !== null;

  const [shown, setShown] = useState(0);

  // The detail types out in ~1.5s regardless of length: this effect resets and
  // then drives `shown` as an animation, so synchronous setState in the effect
  // body is intentional (same pattern as digithings-web's ModuleManifest).
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!open) {
      setShown(0);
      return;
    }
    if (!safe) {
      setShown(out.length);
      return;
    }
    setShown(0);
    let i = 0;
    const step = Math.max(2, Math.ceil(out.length / 90));
    const id = window.setInterval(() => {
      i += step;
      if (i >= out.length) {
        i = out.length;
        window.clearInterval(id);
      }
      setShown(i);
    }, 16);
    return () => window.clearInterval(id);
  }, [open, out, safe]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const select = (id: string) => {
    const next = sel === id ? null : id;
    if (selectedId === undefined) setOwnSel(next);
    onSelect?.(next);
  };

  const hasPorts = rows.some((r) => r.port !== undefined);
  const anim = animateRows && safe;
  const shell = ["tm", hasPorts ? "has-ports" : "", anim ? "" : "no-anim", className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={shell} aria-label={ariaLabel}>
      <div className="tm-pane flex flex-col rounded-[16px] border border-hair px-[clamp(1rem,2.4vw,1.6rem)] py-[clamp(1rem,2.4vw,1.5rem)] font-mono">
        <div className="mb-[0.7rem] flex-none text-[0.8rem] tracking-[0.02em] text-ink-mute">
          <span className="text-accent">{prompt}</span> {command}
          {meta ? <span> {meta}</span> : null}
        </div>
        <div className="tm-body">
          <ol className="tm-rows">
            {rows.map((r, i) => {
              const off = r.status === "roadmap";
              const isSel = sel === r.id;
              return (
                <li
                  key={r.id}
                  className={`tm-row${off ? " is-off" : ""}${isSel ? " is-sel" : ""}`}
                  style={anim ? { animationDelay: `${i * 55}ms` } : undefined}
                >
                  <button
                    type="button"
                    className="tm-row-link"
                    aria-expanded={isSel}
                    onClick={() => select(r.id)}
                  >
                    <span className={`tm-dot${off ? " off" : ""}`} aria-hidden="true" />
                    <span className="tm-name text-[0.92rem] font-medium">
                      <RowName name={r.name} prefix={namePrefix} />
                    </span>
                    {hasPorts ? (
                      <span className="tm-port text-[0.78rem] text-ink-mute">{r.port ?? ""}</span>
                    ) : null}
                    <span className="tm-blurb truncate text-[0.84rem] text-ink-soft">{r.blurb}</span>
                  </button>
                </li>
              );
            })}
          </ol>
          <div className="tm-out">
            <div className="tm-out-show pb-[0.2rem]" aria-live="polite">
              {selRow ? (
                <pre className="tm-out-body m-0 whitespace-pre-wrap break-words font-mono text-[0.84rem] leading-[1.6] text-ink-soft">
                  {out.slice(0, shown)}
                  <span className="tm-cursor" aria-hidden="true" />
                </pre>
              ) : (
                <p className="m-0 text-[0.84rem] text-ink-mute">
                  {hint}
                  <span className="tm-cursor" aria-hidden="true" />
                </p>
              )}
            </div>
            {/* Fragment keeps the slot element out of this children array: an
                element prop arriving across an RSC boundary trips React 19's
                missing-key check when reconciled as a direct array member. */}
            <>{footer}</>
          </div>
        </div>
      </div>
    </div>
  );
}
