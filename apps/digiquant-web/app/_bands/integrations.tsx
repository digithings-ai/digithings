import { CtaLink, Emblem, Marquee } from "@digithings/ui";
import { IntegrationMark, integrationHref, type IntegrationId } from "@/components/integrations/marks";
import { PixelWordmark } from "../../../digithings-web/components/landing/PixelWordmark";
import { Band } from "../_chrome/Band";
import { MCP_TOOLS } from "../_mcp";

const toolCount = (prefix: string) => MCP_TOOLS.filter((t) => t.name.startsWith(prefix)).length;

const CARD =
  "flex h-auto min-h-full w-full min-w-0 shrink flex-col items-stretch gap-2.5 overflow-hidden bg-surface p-[1.15rem] text-start font-sans text-[length:inherit] font-normal whitespace-normal no-underline hover:bg-surface-2";

const DRIVERS: { id: IntegrationId; name: string; role: string; line: string; fact: string }[] = [
  {
    id: "gloomberb",
    name: "Gloomberg",
    role: "market data",
    line: "Quotes, filings, macro and options for the research stages. Enrichment, never the record the backtests run on.",
    fact: `${toolCount("digifetch_")} MCP tools`,
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
];

/** Modules digiquant actually calls. Emblems exist only where the kit already draws one. */
const MODULES: { name: string; line: string; emblem?: string }[] = [
  { name: "digigraph", emblem: "digigraph", line: "Orchestrates the research and portfolio runs." },
  { name: "digichat", emblem: "digichat", line: "The chat where a strategy idea starts." },
  { name: "digillm", line: "Routes and caches the model calls research and the dashboard make." },
  { name: "digikey", emblem: "digikey", line: "Checks the API token on digiquant requests." },
  { name: "digibase", emblem: "digibase", line: "Shared errors, request handling, and metrics on the API." },
  { name: "digifetch", line: "Market-data tools the research stages call through Gloomberg." },
];

const PACKAGES_A = [
  "Coinbase · public price feed",
  "Alpaca · broker adapter",
  "Interactive Brokers · broker adapter",
  "Kraken · account snapshots",
  "Tradier · account snapshots",
];

const PACKAGES_B = [
  "Yahoo Finance · quote history",
  "FRED · macro series",
  "Supabase · stored prices",
  "Binance · chart prices",
];

/** Integrations. digithings is the platform under the agents and the chat.
 *  Gloomberg, LuxAlgo Vela, and NautilusTrader are the three drivers.
 *  The scrolling rows name the other packages this tree actually calls. */
export function IntegrationsBand() {
  return (
    <Band
      id="integrations"
      title="What the engine is built on"
      takeaway="digithings runs the agents, the chat, and the model calls. Gloomberg supplies the data, LuxAlgo Vela the live chart, and NautilusTrader the engine."
    >
      <div className="flex min-w-0 flex-col gap-8">
        <div className="integrations-hero flex min-w-0 flex-col items-center gap-8 border border-hair px-4 py-8 sm:px-8 sm:py-10">
          <CtaLink
            href={integrationHref("digithings")}
            external
            variant="ghost"
            className="h-auto w-fit max-w-full shrink justify-center overflow-visible p-0 hover:bg-transparent"
          >
            <PixelWordmark />
          </CtaLink>
          <p className="m-0 max-w-[36rem] text-center text-[1.05rem] leading-[1.55] text-ink-soft">
            The platform that drives the agentic side of digiquant.
          </p>
          <ul className="m-0 grid w-full list-none gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
            {MODULES.map((mod) => (
              <li key={mod.name} className="flex min-w-0 items-start gap-3">
                {mod.emblem ? <Emblem id={mod.emblem} size={28} className="mt-0.5 shrink-0" /> : null}
                <span className="min-w-0">
                  <span className="block font-mono text-[0.95rem] text-ink">{mod.name}</span>
                  <span className="mt-1 block text-[0.875rem] leading-[1.5] text-ink-soft">{mod.line}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <ul aria-label="Architectural drivers" className="m-0 grid min-w-0 list-none gap-px overflow-x-clip border border-hair bg-hair p-px md:grid-cols-3">
          {DRIVERS.map((d) => (
            <li key={d.id} className="min-w-0">
              <CtaLink href={integrationHref(d.id)} external variant="ghost" className={CARD}>
                <span className="flex items-center gap-3 text-ink">
                  <IntegrationMark id={d.id} size={d.id === "nautilus" ? 36 : 32} />
                  <span className="min-w-0">
                    <span className="block font-display text-[1.25rem] font-medium leading-tight tracking-[-0.02em] text-ink">{d.name}</span>
                    <span className="block font-mono text-[0.68rem] font-normal text-ink-mute">{d.role}</span>
                  </span>
                </span>
                <span className="text-[0.8125rem] font-normal leading-[1.55] text-ink-soft">{d.line}</span>
                <span className="mt-auto border-t border-hair pt-2 font-mono text-[0.68rem] font-normal text-ink-mute">{d.fact}</span>
              </CtaLink>
            </li>
          ))}
        </ul>

        <div className="flex min-w-0 flex-col gap-3" aria-label="Connected packages">
          <Marquee items={PACKAGES_A} direction="left" speed={42} />
          <Marquee items={PACKAGES_B} direction="right" speed={50} />
        </div>
      </div>
    </Band>
  );
}
