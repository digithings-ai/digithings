import { CtaLink } from "@digithings/ui";
import { AssetLogoFor } from "./asset-logo";
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
      className="flex h-full w-full min-w-0 flex-col items-stretch justify-start gap-0 overflow-hidden bg-surface p-0 text-start font-normal whitespace-normal no-underline hover:bg-surface-2"
    >
      <span className="flex items-center gap-2 px-3 py-2">
        <AssetLogoFor strategy={id} symbol={symbol} size={24} />
        <span className="min-w-0">
          <span className="block font-mono text-[0.95rem] font-medium leading-tight tracking-[-0.01em] text-ink">
            {strategyDisplayName(id, label)}
          </span>
          <span className="block font-mono text-[0.68rem] text-ink-mute">{symbol} · unpublished</span>
        </span>
      </span>
      <dl className="m-0 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-hair px-3 py-2">
        {labels.map((name) => (
          <div key={name}>
            <dt className="font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">{name}</dt>
            <dd className="m-0 font-mono text-[0.9rem] leading-none text-ink">—</dd>
          </div>
        ))}
      </dl>
    </CtaLink>
  );
}
