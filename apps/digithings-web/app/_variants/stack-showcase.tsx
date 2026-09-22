"use client";

/**
 * The stack showcase — the bento you liked, given a travelling focus.
 *
 * The grid is still the map (weight by tier, livery per module, roadmap
 * badged), but as the page scrolls one module at a time takes focus: its cell
 * lifts out of the grid and a detail card beside it changes to that module —
 * role, what it does, its real dependency chips, and the compose command that
 * starts it. The next module then takes over. Sticky pinning on the grid is CSS
 * (`.stack-pin` below); the index is read from scroll progress, the same
 * one-line `useScroll` + `useMotionValueEvent` shape the reference specimens use.
 *
 * Honesty notes:
 *  - The dependency chips are the registry's real `stack` list, not prose.
 *  - The compose command is the registry's own `dockerCmd`.
 *  - There is no "live" readout, no invented metric, and no timing.
 *
 * Accessibility: the cells are real links and keyboard-reachable whatever the
 * focus state. Below 900px, and under `prefers-reduced-motion`, it degrades to
 * the plain grid with every cell's detail inline — the showcase is a desktop
 * affordance, not the only way to read the page.
 */
import { useEffect, useRef, useState } from "react";
import { useMotionValueEvent, useScroll } from "motion/react";

import { Emblem, StackRow } from "@digithings/ui";
import { BENTO, MODULE_ROWS, type ModuleRow } from "./content";

/** One grid cell, at the span the bento layout gave it. */
function Cell({
  m,
  span,
  active,
}: {
  m: ModuleRow;
  span: "hero" | "wide" | "tall" | "unit";
  /** The focus state — the grid's travelling highlight. */
  active: boolean;
}) {
  const isHero = span === "hero";
  /** Inline `gridColumn` wins over the `.bento-hero`/`.wide` classes from
   *  data-layout.css: this grid is 5 columns (it sits beside the detail card),
   *  so the kit's 4-column spans would not tile. `gridRow` is left to
   *  `grid-auto-rows`, which stretches every cell in a row to the tallest. */
  const colSpan = span === "hero" || span === "wide" ? 2 : 1;
  return (
    <div
      data-module={m.id}
      className={`bento-cell stack-cell flex min-h-[7rem] flex-col justify-between gap-[1rem] p-[1.05rem]${
        active ? " is-active" : ""
      }`}
      style={{ gridColumn: `span ${colSpan}` }}
    >
      <div className="flex items-start justify-between gap-[0.6rem]">
        <Emblem id={m.emblem} size={isHero ? 24 : 15} />
        {m.tier === "roadmap" ? (
          <span className="font-mono text-[0.5rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
            roadmap
          </span>
        ) : null}
      </div>
      <div>
        <p className={`m-0 font-mono leading-[1.2] text-ink ${isHero ? "text-[1.02rem]" : "text-[0.8rem]"}`}>
          {m.name}
        </p>
        {/* Only the wide cells have room for the role line; the units were
            deliberately kept to name + mark so eleven of them stay legible at
            this size (the detail card carries the role for all of them). */}
        {colSpan === 2 ? (
          <p className="mt-[0.6rem] mb-0 font-mono text-[0.6rem] leading-[1.45] uppercase tracking-[0.06em] text-ink-mute">
            {m.roleShort}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/** The detail card: everything you cannot fit in a cell. */
function Detail({ m, index }: { m: ModuleRow; index: number }) {
  return (
    <div className="flex h-full min-h-[27rem] flex-col border border-hair bg-surface p-[1.5rem]">
      <div className="flex items-baseline justify-between gap-[0.8rem]">
        <span className="font-mono text-[0.6rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
          {String(index + 1).padStart(2, "0")} / {String(MODULE_ROWS.length).padStart(2, "0")}
        </span>
        <span
          className={`border border-hair px-[0.5rem] py-[0.1rem] font-mono text-[0.55rem] uppercase tracking-[var(--tracking-meta)] ${
            m.tier === "roadmap" ? "text-ink-mute" : "text-ink-soft"
          }`}
        >
          {m.tier}
        </span>
      </div>

      <div className="mt-[1.3rem] flex items-center gap-[0.7rem]">
        <Emblem id={m.emblem} size={24} />
        <span className="font-mono text-[1.2rem] text-ink">{m.name}</span>
      </div>

      <p className="mt-[0.6rem] mb-0 font-mono text-[0.65rem] leading-[1.5] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
        {m.role}
      </p>
      <p className="mt-[1.2rem] mb-0 text-[0.93rem] leading-[1.8] text-ink-soft">{m.tagline}</p>

      <div className="mt-auto pt-[1.8rem]">
        <span className="font-mono text-[0.6rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
          depends on
        </span>
        <div className="mt-[0.8rem]">
          <StackRow items={m.stack} />
        </div>
      </div>

      {m.dockerCmd ? (
        <div className="mt-[1.4rem] border-t border-hair pt-[1rem]">
          <span className="font-mono text-[0.6rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
            start it
          </span>
          <p className="mt-[0.6rem] mb-0 font-mono text-[0.82rem] leading-[1.6] break-words text-ink">
            {m.dockerCmd}
          </p>
        </div>
      ) : null}
    </div>
  );
}

/** The small-screen / reduced-motion reading: the grid, then every detail. */
function Fallback() {
  return (
    <>
      <div className="bento-grid">
        {BENTO.map(({ id, span }) => {
          const m = MODULE_ROWS.find((r) => r.id === id);
          if (!m) return null;
          return <Cell key={id} m={m} span={span} active={false} />;
        })}
      </div>
      <div className="mt-[1.4rem] grid gap-[1rem]">
        {MODULE_ROWS.map((m, i) => (
          <div key={m.id} className="min-h-[18rem]">
            <Detail m={m} index={i} />
          </div>
        ))}
      </div>
    </>
  );
}

export function StackShowcase({ className }: { className?: string }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [idx, setIdx] = useState(0);
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    const mq = matchMedia("(max-width: 900px), (prefers-reduced-motion: reduce)");
    const apply = () => setCompact(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const { scrollYProgress } = useScroll({ target: trackRef, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (p) => {
    const n = MODULE_ROWS.length;
    setIdx((prev) => {
      const next = Math.max(0, Math.min(n - 1, Math.floor(p * n)));
      return next === prev ? prev : next;
    });
  });

  const active = MODULE_ROWS[idx];

  if (compact) return <Fallback />;

  return (
    <div ref={trackRef} style={{ height: `${MODULE_ROWS.length * 72}vh` }} className={className}>
      <div className="stack-pin">
        <div className="grid items-stretch gap-[1.4rem] min-[1180px]:grid-cols-[minmax(0,1fr)_21rem]">
          <div
            className="stack-grid self-center"
            data-active={active.id}
            style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}
          >
            {BENTO.map(({ id, span }) => {
              const m = MODULE_ROWS.find((r) => r.id === id);
              if (!m) return null;
              return <Cell key={id} m={m} span={span} active={m.id === active.id} />;
            })}
          </div>
          <div className="grid">
            <Detail m={active} index={idx} />
          </div>
        </div>
      </div>
    </div>
  );
}
