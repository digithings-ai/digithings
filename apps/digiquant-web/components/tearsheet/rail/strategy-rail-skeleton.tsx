/** Designed placeholder rail: skeleton cards that read as tearsheet cards, with
 *  every bar a neutral outline (no numbers, no fabricated values). The label
 *  says exactly why it is empty. Static: no animation, so it is the same under
 *  reduced motion and with no JS. */
const KPI_LABELS = ["CAGR", "Max DD", "Profit factor", "Win rate", "Avg trade", "Trades"] as const;

function SkeletonCard({ index }: { index: number }) {
  return (
    <div
      aria-hidden="true"
      className="flex h-full flex-col gap-4 border border-dashed border-hair p-4"
      style={{ opacity: 1 - index * 0.12 }}
    >
      <div className="flex items-center gap-3">
        <span className="size-8 shrink-0 border border-hair" />
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <span className="h-3 w-3/4 border border-hair" />
          <span className="h-2 w-1/2 border border-hair" />
        </div>
      </div>
      <dl className="m-0 grid grid-cols-2 gap-x-4 gap-y-3">
        {KPI_LABELS.map((label) => (
          <div key={label} className="flex flex-col gap-1">
            <dt className="text-[0.65rem] uppercase tracking-wide text-ink-mute">{label}</dt>
            <dd className="m-0 font-mono text-ink-mute">&mdash;</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function StrategyRailSkeleton({ message }: { message: string }) {
  return (
    <div className="grid gap-3">
      <p role="status" className="m-0 font-mono text-[0.75rem] text-ink-soft">
        {message}
      </p>
      <div className="flex gap-4 overflow-hidden" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="w-[min(82vw,20rem)] flex-none">
            <SkeletonCard index={i} />
          </div>
        ))}
      </div>
    </div>
  );
}
