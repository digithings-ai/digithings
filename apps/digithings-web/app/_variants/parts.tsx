import type { ReactNode } from "react";

import { Emblem, ProductFrame } from "@digithings/ui";
import { COUNTS, type ModuleRow } from "./content";

/**
 * The parts every variant draws on (exploration, 2026-09-21). Nothing here is
 * production: the four width registers exist so a variant can be switched
 * between them with one wrapper, and the crops exist so a variant can show a
 * claim's evidence instead of describing it.
 *
 * Utilities only, no app CSS, and no new part — if something in here survives
 * the picking, it gets promoted into `packages/ui` with tests rather than
 * copied into `/`.
 */

/* ------------------------------------------------------------------ width */

type FrameProps = { children: ReactNode; className?: string };

/** Full-bleed: gutters only, no max-width. */
export function Bleed({ children, className }: FrameProps) {
  return <div className={`w-full px-[var(--page-pad)]${className ? ` ${className}` : ""}`}>{children}</div>;
}

/** Wide: the 1280 register. */
export function Wide({ children, className }: FrameProps) {
  return (
    <div className={`mx-auto w-full max-w-[var(--wrap-wide)] px-[var(--page-pad)]${className ? ` ${className}` : ""}`}>
      {children}
    </div>
  );
}

/** Document: the 1180 register (the site's current `--frame-w`). */
export function Doc({ children, className }: FrameProps) {
  return (
    <div className={`mx-auto w-full max-w-[var(--frame-w)] px-[var(--page-pad)]${className ? ` ${className}` : ""}`}>
      {children}
    </div>
  );
}

/** Editorial: the prose measure. */
export function Narrow({ children, className }: FrameProps) {
  return (
    <div className={`mx-auto w-full max-w-[var(--measure-prose)] px-[var(--page-pad)]${className ? ` ${className}` : ""}`}>
      {children}
    </div>
  );
}

/* -------------------------------------------------------------- furniture */

/** The uppercase mono block label the reference puts on every specimen. */
export function BlockLabel({ children }: { children: ReactNode }) {
  return (
    <p className="m-0 font-mono text-[length:var(--type-meta)] tracking-[var(--tracking-meta)] uppercase text-ink-mute">
      {children}
    </p>
  );
}

/** Section heading at the document scale, with an optional lede. */
export function Heading({ title, lede }: { title: ReactNode; lede?: ReactNode }) {
  return (
    <>
      <h2 className="m-0 max-w-[var(--measure-prose)] font-mono text-[length:var(--type-section)] font-medium leading-[1.35] tracking-[-0.01em] text-ink">
        {title}
      </h2>
      {lede ? (
        <p className="mt-[0.9rem] mb-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
          {lede}
        </p>
      ) : null}
    </>
  );
}

/** A hairline-separated block: the reference's bordered specimen frame. */
export function Specimen({
  label,
  children,
  className,
}: {
  label?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`border border-hair bg-surface p-[1.25rem]${className ? ` ${className}` : ""}`}>
      {label ? (
        <div className="mb-[1rem]">
          <BlockLabel>{label}</BlockLabel>
        </div>
      ) : null}
      {children}
    </div>
  );
}

/** The reference's honesty badge for illustrative content. */
export function ExampleBadge({ children = "Example data · not live" }: { children?: ReactNode }) {
  return (
    <span className="inline-block border border-hair px-[0.6rem] py-[0.15rem] font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
      {children}
    </span>
  );
}

/** One module as a bare name + emblem, for tight rows and chip strips. */
export function ModuleChip({ m }: { m: ModuleRow }) {
  return (
    <span className="flex items-center gap-[0.5rem] border border-hair px-[0.6rem] py-[0.35rem] font-mono text-[0.75rem] text-ink-soft">
      <Emblem id={m.emblem} size={14} />
      {m.name}
    </span>
  );
}

/* ------------------------------------------------------- artefact crops --
 * Each crop is a faithful excerpt of a file in this repository. They are not
 * mockups of a UI: the compose table is docker-compose.yml's own services and
 * loopback bindings, the BYOK lines are the provider contract and the two
 * storage keys the site actually writes, and the audit line is the shape of
 * digibase.audit's AuditEvent. The frame's tag names the file, so the
 * provenance travels with the picture.
 * ---------------------------------------------------------------------- */

export function ComposeCrop() {
  const rows: [string, string][] = [
    ["digigraph", "127.0.0.1:8000"],
    ["digiquant", "127.0.0.1:8001"],
    ["digisearch", "127.0.0.1:8002"],
    ["digismith", "127.0.0.1:8003"],
    ["digivault", "127.0.0.1:8004"],
    ["digikey", "127.0.0.1:8005"],
    ["litellm", "127.0.0.1:4000"],
  ];
  return (
    <ProductFrame tag="docker-compose.yml">
      <div className="flex h-full w-full flex-col gap-[10px] p-[22px] font-mono text-[15px] leading-[1.5]">
        <div className="flex justify-between text-[12px] uppercase tracking-[0.14em] text-ink-mute">
          <span>service</span>
          <span>published on</span>
        </div>
        {rows.map(([service, bind]) => (
          <div key={service} className="flex justify-between border-t border-hair pt-[7px]">
            <span className="text-ink">{service}</span>
            <span className="text-ink-soft">{bind}</span>
          </div>
        ))}
        <div className="mt-auto pt-[12px] text-ink-mute">
          {COUNTS.compose} services · none on 0.0.0.0
        </div>
      </div>
    </ProductFrame>
  );
}

export function ByokCrop() {
  return (
    <ProductFrame tag="byok · provider contract">
      <div className="flex h-full w-full flex-col gap-[10px] p-[22px] font-mono text-[15px] leading-[1.5]">
        <div className="border-t border-hair pt-[7px]">
          <span className="text-ink-mute">provider </span>
          <span className="text-ink">openrouter · openai · anthropic · gemini · xai</span>
        </div>
        <div className="border-t border-hair pt-[7px]">
          <span className="text-ink-mute">key </span>
          <span className="text-ink">●●●●●●●●●●●● in memory, this tab only</span>
        </div>
        <div className="border-t border-hair pt-[7px]">
          <span className="text-ink-mute">written </span>
          <span className="text-ink">digichat:provider, digichat:model</span>
        </div>
        <div className="mt-auto text-ink-mute">
          never persisted · {COUNTS.keysStored} stored
        </div>
      </div>
    </ProductFrame>
  );
}

export function AuditCrop() {
  return (
    <ProductFrame tag="events.jsonl">
      <div className="flex h-full w-full flex-col gap-[10px] p-[22px] font-mono text-[14px] leading-[1.6]">
        <div className="text-ink">
          {"{"}
          <span className="text-ink-mute">&quot;ts&quot;</span>: &quot;2026-09-20T21:04:11Z&quot;,{" "}
          <span className="text-ink-mute">&quot;event_type&quot;</span>: &quot;workflow_start&quot;,
        </div>
        <div className="pl-[16px] text-ink">
          <span className="text-ink-mute">&quot;agent_id&quot;</span>: &quot;digigraph&quot;,{" "}
          <span className="text-ink-mute">&quot;tenant&quot;</span>: &quot;default&quot;,
        </div>
        <div className="pl-[16px] text-ink">
          <span className="text-ink-mute">&quot;payload&quot;</span>: {"{"}{" "}
          <span className="text-ink-mute">&quot;api_key&quot;</span>: &quot;[REDACTED]&quot; {"}"}
        </div>
        <div className="text-ink">{"}"}</div>
        <div className="mt-auto border-t border-hair pt-[10px] text-ink-mute">
          redacted by key name: password · api_key · token · secret
        </div>
      </div>
    </ProductFrame>
  );
}
