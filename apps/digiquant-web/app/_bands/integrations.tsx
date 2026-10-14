import { CtaLink, Marquee } from "@digithings/ui";
import {
  IntegrationMark,
  RowMark,
  integrationHref,
  type IntegrationId,
  type RowProviderId,
} from "@/components/integrations/marks";
import { Band } from "../_chrome/Band";

<<<<<<< HEAD
const DRIVERS: { id: IntegrationId; name: string; role: string }[] = [
  { id: "gloomberb", name: "Gloomberg", role: "market data" },
  { id: "luxalgo", name: "LuxAlgo", role: "live chart" },
  { id: "nautilus", name: "NautilusTrader", role: "engine" },
=======
const toolCount = (prefix: string) => MCP_TOOLS.filter((t) => t.name.startsWith(prefix)).length;

const CARD =
  "flex h-auto min-h-full w-full min-w-0 shrink flex-col items-stretch gap-2.5 overflow-hidden bg-surface p-[1.15rem] text-start font-sans text-[length:inherit] font-normal whitespace-normal no-underline hover:bg-surface-2";

const DRIVERS: { id: IntegrationId; name: string; role: string; line: string; fact: string }[] = [
  {
    id: "gloomberb",
    name: "Gloomberg",
    role: "market data",
    line: "Quotes, filings, macro and options for the research stages. Enrichment, never the record the backtests run on.",
    fact: `${toolCount("gloomberb_")} MCP tools`,
  },
  {
    id: "luxalgo",
    name: "LuxAlgo",
    role: "Vela backbone · live signals",
    line: "The live chart is the hero.",
    fact: `${toolCount("luxalgo_")} MCP tools · live on hero`,
  },
  {
    id: "nautilus",
    name: "NautilusTrader",
    role: "engine",
    line: "The event-driven engine every backtest and optimize run goes through. One engine, no second code path.",
    fact: "validate → backtest → optimize → export",
  },
>>>>>>> origin/develop
];

/** Modules digiquant calls. Names only — the hero banners do not fit this band. */
const MODULES = ["digigraph", "digichat", "digillm", "digikey", "digibase", "digifetch"] as const;

export type PackageEntry = { id: RowProviderId; label: string };

/** Other connections, each once. Drivers and digithings modules stay above. */
export const PACKAGES_A: PackageEntry[] = [
  { id: "coinbase", label: "Coinbase" },
  { id: "yahoo", label: "Yahoo Finance" },
  { id: "binance", label: "Binance" },
  { id: "cloudflare", label: "Cloudflare" },
  { id: "stripe", label: "Stripe" },
  { id: "optuna", label: "Optuna" },
];

export const PACKAGES_B: PackageEntry[] = [
  { id: "alpaca", label: "Alpaca" },
  { id: "ibkr", label: "Interactive Brokers" },
  { id: "kraken", label: "Kraken" },
  { id: "tradier", label: "Tradier" },
  { id: "supabase", label: "Supabase" },
];

function RowItem({ entry }: { entry: PackageEntry }) {
  return (
    <span className="inline-flex items-center gap-[0.55rem] font-mono text-[0.82rem] whitespace-nowrap text-ink-soft">
      <RowMark id={entry.id} />
      {entry.label}
    </span>
  );
}

/** Integrations, one viewport: platform, the modules this stack calls,
 *  three drivers, then two logo rows for every other connection. */
export function IntegrationsBand() {
  return (
    <Band
      id="integrations"
      title="What the engine is built on"
      takeaway="digithings, the modules digiquant calls, then Gloomberg, LuxAlgo and NautilusTrader."
    >
      <div className="flex min-w-0 flex-col gap-4">
        <div className="flex min-w-0 flex-col gap-3 border border-hair px-4 py-4">
          <CtaLink
            href={integrationHref("digithings")}
            external
            variant="ghost"
            className="h-auto w-fit shrink justify-start gap-2 p-0 hover:bg-transparent"
          >
            <IntegrationMark id="digithings" size={22} />
            <span className="font-display text-[1.15rem] font-medium tracking-[-0.02em] text-ink">digithings</span>
          </CtaLink>
          <ul aria-label="digiquant calls" className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
            {MODULES.map((name) => (
              <li key={name} className="font-mono text-[0.82rem] text-ink">{name}</li>
            ))}
          </ul>
        </div>

        <ul aria-label="Architectural drivers" className="m-0 grid min-w-0 list-none gap-px overflow-x-clip border border-hair bg-hair p-px md:grid-cols-3">
          {DRIVERS.map((d) => (
            <li key={d.id} className="min-w-0">
              <CtaLink
                href={integrationHref(d.id)}
                external
                variant="ghost"
                className="flex h-auto w-full min-w-0 items-center gap-3 bg-surface px-3 py-3 text-start whitespace-normal no-underline hover:bg-surface-2"
              >
                <IntegrationMark id={d.id} size={28} />
                <span className="min-w-0">
                  <span className="block font-display text-[1.05rem] font-medium leading-tight text-ink">{d.name}</span>
                  <span className="block font-mono text-[0.68rem] text-ink-mute">{d.role}</span>
                </span>
              </CtaLink>
            </li>
          ))}
        </ul>

        <div className="flex min-w-0 flex-col gap-3" aria-label="Connected packages">
          <Marquee className="mq-fill" direction="left" speed={42}>
            {PACKAGES_A.map((entry) => (
              <RowItem key={entry.id} entry={entry} />
            ))}
          </Marquee>
          <Marquee className="mq-fill" direction="right" speed={50}>
            {PACKAGES_B.map((entry) => (
              <RowItem key={entry.id} entry={entry} />
            ))}
          </Marquee>
        </div>
      </div>
    </Band>
  );
}
