import { DESK_TOUR } from "@/lib/showcase";

/** Static dashboard display — Gloomberg-ish hairline mock, not a tool SPA. */
export function DeskTour() {
  return (
    <figure className="product-frame max-w-[var(--wrap)]">
      <div className="product-frame__surface p-0">
        <div className="flex items-center gap-[0.9rem] border-b border-hair px-[1rem] py-[0.65rem] font-mono text-[0.68rem] uppercase tracking-[0.12em] text-ink-mute">
          {DESK_TOUR.surfaces.map((surface) => (
            <span key={surface} className={surface === "house" ? "text-ink" : undefined}>
              {surface}
            </span>
          ))}
          <span className="ml-auto text-accent">{DESK_TOUR.mode}</span>
        </div>

        <div className="grid min-[720px]:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)_minmax(0,0.9fr)]">
          <div className="border-hair px-[1rem] py-[1rem] min-[720px]:border-r">
            <p className="font-mono text-[0.62rem] uppercase tracking-[0.14em] text-accent">
              compose
            </p>
            <p className="mt-[0.7rem] font-mono text-[0.82rem] leading-[1.55] text-ink">
              <span className="text-accent">›</span> {DESK_TOUR.prompt}
            </p>
            <p className="mt-[0.85rem] font-mono text-[0.7rem] text-ink-mute">
              digichat · demo
            </p>
          </div>

          <div className="border-t border-hair px-[1rem] py-[1rem] min-[720px]:border-t-0 min-[720px]:border-r">
            <p className="font-mono text-[0.62rem] uppercase tracking-[0.14em] text-accent">
              book
            </p>
            <ul className="mt-[0.7rem] grid gap-[0.45rem] font-mono text-[0.78rem] text-ink">
              {DESK_TOUR.book.map((row) => (
                <li
                  key={row.symbol}
                  className="grid grid-cols-[2.4rem_1fr_auto] gap-[0.6rem] border-b border-hair pb-[0.4rem] last:border-0 last:pb-0"
                >
                  <span>{row.symbol}</span>
                  <span className="text-ink-soft">{row.sleeve}</span>
                  <span className="text-ink-mute">{row.state}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="border-t border-hair px-[1rem] py-[1rem] min-[720px]:border-t-0">
            <p className="font-mono text-[0.62rem] uppercase tracking-[0.14em] text-accent">
              journal
            </p>
            <ul className="mt-[0.7rem] grid gap-[0.55rem] font-mono text-[0.78rem] text-ink-soft">
              {DESK_TOUR.journal.map((row) => (
                <li key={row.when}>
                  <span className="text-ink-mute">{row.when}</span> {row.note}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
      <figcaption className="product-frame__caption">{DESK_TOUR.caption}</figcaption>
    </figure>
  );
}
