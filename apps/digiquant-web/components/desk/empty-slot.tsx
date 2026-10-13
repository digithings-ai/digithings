import { DASH, EMPTY_READ } from "../../../../clients/digiquant-tui/src/read";

/** A browser slot with no official read. Nothing is estimated. */
export function EmptySlot({ title }: { title: string }) {
  return (
    <section aria-label={title} className="m-px flex min-h-0 flex-1 flex-col bg-surface">
      <h1 className="m-0 flex h-7 shrink-0 items-center border-b border-hair px-2.5 font-mono text-[0.6875rem] font-normal tracking-[0.04em] text-ink-mute">{title}</h1>
      <p className="m-0 px-2.5 py-1.5 font-mono text-[0.75rem] leading-[1.45] text-ink tabular-nums">{DASH}</p>
      <p className="m-0 px-2.5 pb-2 font-mono text-[0.75rem] leading-[1.45] text-ink-mute">{EMPTY_READ}</p>
    </section>
  );
}
