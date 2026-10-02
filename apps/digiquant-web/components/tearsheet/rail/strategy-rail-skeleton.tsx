/** Designed placeholder rail: skeleton cards that read as tearsheet cards, with
 *  every bar a neutral outline (no numbers, no fabricated values). The label
 *  says exactly why it is empty. Static: no animation, so it is the same under
 *  reduced motion and with no JS. */
const KPI_LABELS = ["CAGR", "Max DD", "Profit factor", "Win rate", "Avg trade", "Trades"] as const;

function SkeletonCard({ index }: { index: number }) {
  return (
    <div
      aria-hidden="true"
      className="flex h-full flex-col gap-0 border border-dashed border-hair"
      style={{ opacity: 1 - index * 0.12 }}
    >
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="size-6 shrink-0 border border-hair" />
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span className="h-3 w-3/4 border border-hair" />
          <span className="h-2 w-1/2 border border-hair" />
        </div>
      </div>
      <dl className="m-0 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-hair px-3 py-2">
        {KPI_LABELS.map((label) => (
          <div key={label} className="flex flex-col gap-1">
            <dt className="font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">{label}</dt>
            <dd className="m-0 font-mono text-[0.9rem] leading-none text-ink-mute">&mdash;</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function StrategyRailSkeleton({ message }: { message: string }) {
  return (
    <div className="grid gap-2">
      <p role="status" className="m-0 font-mono text-[0.66rem] text-ink-mute">
        {message}
      </p>
      <div className="flex gap-2 overflow-hidden" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="w-[min(82vw,18.5rem)] flex-none">
            <SkeletonCard index={i} />
          </div>
        ))}
      </div>
    </div>
  );
}
