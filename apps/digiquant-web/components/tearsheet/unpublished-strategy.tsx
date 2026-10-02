import { CtaLink } from "@digithings/ui";
import { ALLOCATED_KPI_LABEL, TOTAL_RETURN_KPI_LABEL, VS_LUMP_KPI_LABEL } from "./dca";
import { strategyDisplayName } from "./strategy-names";

const LS = ["CAGR", "Max DD", "Profit factor", "Win rate", "Avg trade", "Trades"] as const;
const DCA = [TOTAL_RETURN_KPI_LABEL, "Max DD", VS_LUMP_KPI_LABEL, ALLOCATED_KPI_LABEL] as const;

/** A strategy route with no published tearsheet. Every statistic is an em dash. */
export function UnpublishedStrategyCard({ id, label, symbol }: { id: string; label: string; symbol: string }) {
  const dca = id.includes("sdca");
  const labels = dca ? DCA : LS;
  return (
    <CtaLink
      href={`/strategies/${id}/`}
      variant="ghost"
      className="flex h-auto min-h-full w-full min-w-0 flex-col items-stretch gap-3 overflow-hidden border border-hair bg-surface p-4 text-start whitespace-normal no-underline hover:bg-surface-2"
    >
      <span className="font-display text-[1.05rem] font-medium leading-tight text-ink">
        {strategyDisplayName(id, label)}
      </span>
      <span className="font-mono text-[0.66rem] text-ink-mute">
        {symbol} · unpublished
      </span>
      <dl className="m-0 grid grid-cols-2 gap-x-4 gap-y-2">
        {labels.map((name) => (
          <div key={name}>
            <dt className="font-mono text-[0.6rem] uppercase tracking-wide text-ink-mute">{name}</dt>
            <dd className="m-0 font-mono text-[0.85rem] text-ink-soft">—</dd>
          </div>
        ))}
      </dl>
    </CtaLink>
  );
}
