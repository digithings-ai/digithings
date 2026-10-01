import type { StageSnapshot } from "@/lib/run-snapshot";
import { STAGE_COPY } from "./stage-copy";

/** One stage on the track: index label, what it does, its sub-steps, and what the
 *  recorded run holds for it (status and count; titles only where the snapshot allows). */
export function StageCard({
  index,
  total,
  name,
  recorded,
  hasRun,
}: {
  index: number;
  total: number;
  name: keyof typeof STAGE_COPY;
  recorded: StageSnapshot | undefined;
  hasRun: boolean;
}) {
  const copy = STAGE_COPY[name];
  const n = String(index + 1).padStart(2, "0");
  return (
    <article aria-label={`Stage ${index + 1} of ${total}: ${name}`} className="flex h-full w-full min-w-0 flex-col border border-hair bg-surface">
      <div className="flex items-baseline justify-between border-b border-hair px-3 py-1.5 font-mono text-[0.64rem] text-ink-mute">
        <span>
          {n}/{String(total).padStart(2, "0")}
        </span>
        <span>{hasRun ? (recorded?.status === "recorded" ? "recorded" : "not recorded") : "no recorded run"}</span>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <h3 className="m-0 font-display text-[1.05rem] font-medium leading-tight tracking-[-0.02em] text-ink">{name}</h3>
        <p className="m-0 line-clamp-3 text-[0.75rem] leading-[1.5] text-ink-soft">{copy.does}</p>
        <ul className="m-0 flex list-none flex-col gap-1 p-0 font-mono text-[0.66rem] text-ink-soft">
          {copy.steps.slice(0, 2).map((s) => (
            <li key={s} className="flex gap-2 border-t border-hair pt-1">
              <span aria-hidden="true" className="text-ink-mute">
                ▸
              </span>
              {s}
            </li>
          ))}
          {copy.steps.length > 2 ? <li className="pt-1 text-ink-mute">+{copy.steps.length - 2} more</li> : null}
        </ul>
        <div className="mt-auto border-t border-hair pt-2 font-mono text-[0.64rem] text-ink-mute">
          {recorded ? (
            <>
              <p className="m-0 text-ink-soft">
                {recorded.documentCount} {recorded.documentCount === 1 ? "document" : "documents"} in the recorded run
              </p>
              {recorded.titles && recorded.titles.length > 0 ? (
                <ul className="m-0 mt-1 flex list-none flex-col gap-0.5 p-0">
                  {recorded.titles.slice(0, 2).map((t) => (
                    <li key={t} className="truncate">
                      {t}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p className="m-0">run detail: none recorded in this build</p>
          )}
        </div>
      </div>
    </article>
  );
}

/** The dashed last card: execution is not built. */
export function ExecutionCard({ index, total, status }: { index: number; total: number; status: string }) {
  const n = String(index + 1).padStart(2, "0");
  return (
    <article aria-label={`Stage ${index + 1} of ${total}: Execution, ${status}`} className="flex h-full w-full min-w-0 flex-col border border-dashed border-hair bg-transparent">
      <div className="flex items-baseline justify-between border-b border-dashed border-hair px-3 py-1.5 font-mono text-[0.64rem] text-ink-mute">
        <span>
          {n}/{String(total).padStart(2, "0")}
        </span>
        <span>{status}</span>
      </div>
      <div className="flex flex-1 flex-col gap-3 p-3">
        <h3 className="m-0 font-display text-[1.05rem] font-medium leading-tight tracking-[-0.02em] text-ink-soft">Execution</h3>
        <p className="m-0 text-[0.75rem] leading-[1.5] text-ink-mute">
          Not built. The six stages end in a recorded decision; nothing places an order.
        </p>
      </div>
    </article>
  );
}
