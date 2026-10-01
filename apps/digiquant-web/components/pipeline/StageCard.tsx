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
    <article aria-label={`Stage ${index + 1} of ${total}: ${name}`} className="flex min-h-[25rem] w-full flex-col border border-hair bg-surface font-mono">
      <div className="flex items-baseline justify-between border-b border-hair px-4 py-2 text-[0.68rem] text-ink-mute">
        <span>
          {n}/{String(total).padStart(2, "0")}
        </span>
        <span>{hasRun ? (recorded?.status === "recorded" ? "recorded" : "not recorded") : "no recorded run"}</span>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-4">
        <h3 className="m-0 text-[1.25rem] font-normal leading-tight text-ink">{name}</h3>
        <p className="m-0 text-[0.78rem] leading-[1.6] text-ink-soft">{copy.does}</p>
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[0.72rem] text-ink-soft">
          {copy.steps.map((s) => (
            <li key={s} className="flex gap-2 border-t border-hair pt-1">
              <span aria-hidden="true" className="text-ink-mute">
                ▸
              </span>
              {s}
            </li>
          ))}
        </ul>
        <div className="mt-auto border-t border-hair pt-3 text-[0.68rem] text-ink-mute">
          {recorded ? (
            <>
              <p className="m-0 text-ink-soft">
                {recorded.documentCount} {recorded.documentCount === 1 ? "document" : "documents"} in the recorded run
              </p>
              {recorded.titles && recorded.titles.length > 0 ? (
                <ul className="m-0 mt-1 flex list-none flex-col gap-0.5 p-0">
                  {recorded.titles.slice(0, 4).map((t) => (
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
    <article aria-label={`Stage ${index + 1} of ${total}: Execution, ${status}`} className="flex min-h-[25rem] w-full flex-col border border-dashed border-hair bg-transparent font-mono">
      <div className="flex items-baseline justify-between border-b border-dashed border-hair px-4 py-2 text-[0.68rem] text-ink-mute">
        <span>
          {n}/{String(total).padStart(2, "0")}
        </span>
        <span>{status}</span>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-4">
        <h3 className="m-0 text-[1.25rem] font-normal leading-tight text-ink-soft">Execution</h3>
        <p className="m-0 text-[0.78rem] leading-[1.6] text-ink-mute">
          Not built. The six stages end in a recorded decision; nothing here places an order, and there is no live trading.
        </p>
      </div>
    </article>
  );
}
