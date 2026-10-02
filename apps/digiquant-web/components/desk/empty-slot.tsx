import { DASH, EMPTY_READ } from "../../../../clients/digiquant-tui/src/read";

/** A browser slot with no official read. Nothing is estimated. */
export function EmptySlot({ title }: { title: string }) {
  return (
    <section aria-label={title} className="m-1 flex min-h-0 flex-1 flex-col border border-hair bg-surface">
      <h1 className="m-0 border-b border-hair px-2 py-1 text-[0.65rem] font-normal text-ink-mute">{title}</h1>
      <p className="m-0 px-2 py-2 text-[0.85rem] text-ink">{DASH}</p>
      <p className="m-0 px-2 pb-2 text-[0.7rem] text-ink-mute">{EMPTY_READ}</p>
    </section>
  );
}
