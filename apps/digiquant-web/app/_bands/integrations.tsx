import { CtaLink } from "@digithings/ui";
import { IntegrationMark, integrationHref, type IntegrationId } from "@/components/integrations/marks";
import { Band } from "../_chrome/Band";
import { MCP_TOOLS } from "../_mcp";

const toolCount = (prefix: string) => MCP_TOOLS.filter((t) => t.name.startsWith(prefix)).length;

const CARD =
  "flex h-auto min-h-full w-full flex-col items-stretch gap-3 border border-hair bg-surface p-[1.3rem] text-start font-sans text-[length:inherit] font-normal no-underline hover:bg-surface-2";

const DRIVERS: { id: IntegrationId; name: string; role: string; line: string; fact: string; visual: string }[] = [
  {
    id: "gloomberb",
    name: "Gloomberg",
    role: "market data",
    line: "Quotes, filings, macro and options for the research stages. Enrichment, never the record the backtests run on.",
    fact: `${toolCount("digifetch_")} MCP tools`,
    visual: "Terminal-style quote strip with sparkline — live market context feed.",
  },
  {
    id: "luxalgo",
    name: "LuxAlgo",
    role: "Vela backbone · live signals",
    line: "Real Vela engine behind the hero chart and every signal overlay. Price engine + indicator backbone digiquant research runs on — not a demo card.",
    fact: `${toolCount("luxalgo_")} MCP tools · live on hero`,
    visual: "Live Vela candlestick preview — same engine as the hero chart.",
  },
  {
    id: "nautilus",
    name: "NautilusTrader",
    role: "engine",
    line: "The event-driven engine every backtest and optimize run goes through. One engine, no second code path.",
    fact: "validate → backtest → optimize → export",
    visual: "Backtest run timeline — validate, backtest, optimize, export.",
  },
];

const DIGITHINGS: { label: string; line: string }[] = [
  { label: "agentic workflows", line: "digigraph orchestrates the research and portfolio runs" },
  { label: "chatbot", line: "digichat is where a strategy idea starts" },
  { label: "AI infra", line: "digillm routes and caches every model call; MCP exposes the tools" },
];

const SECONDARY: { id: IntegrationId; name: string; role: string }[] = [
  { id: "coinbase", name: "Coinbase", role: "public price feed" },
  { id: "alpaca", name: "Alpaca", role: "broker adapter" },
  { id: "ibkr", name: "Interactive Brokers", role: "broker adapter" },
];

/** Integrations: the only band that names partners. The three architectural drivers lead,
 *  digithings follows as the platform under the agents and chat, brokers and feeds sit
 *  last and quiet. Showcase only: nothing here places an order. LuxAlgo Vela is the live
 *  price backbone (see the hero), not a demo widget. */
export function IntegrationsBand() {
  return (
    <Band
      id="integrations"
      status="showcase only"
      title="What the engine is built on"
      takeaway="Three integrations drive digiquant: Gloomberg for data, LuxAlgo Vela for live signals, NautilusTrader for the engine. digithings runs the agents and the chat around them."
    >
      <div className="flex flex-col gap-4">
        <ul aria-label="Architectural drivers" className="m-0 grid list-none gap-4 p-0 md:grid-cols-3">
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
                <span
                  aria-hidden="true"
                  className="block overflow-hidden border border-hair bg-term-bg px-3 py-2 font-mono text-[0.66rem] leading-[1.5] text-ink-mute"
                >
                  {d.visual}
                </span>
                <span className="text-[0.8125rem] font-normal leading-[1.55] text-ink-soft">{d.line}</span>
                <span className="mt-auto border-t border-hair pt-2 font-mono text-[0.68rem] font-normal text-ink-mute">{d.fact}</span>
              </CtaLink>
            </li>
          ))}
        </ul>

        <div className="grid gap-4 border border-hair p-[1.3rem] md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <CtaLink href={integrationHref("digithings")} external variant="ghost" className="h-auto items-center justify-start gap-3 p-0 text-start no-underline">
            <span className="text-ink">
              <IntegrationMark id="digithings" size={32} />
            </span>
            <span className="min-w-0">
              <span className="block font-display text-[1.25rem] font-medium leading-tight tracking-[-0.02em] text-ink">digithings</span>
              <span className="block text-[0.8125rem] font-normal leading-[1.55] text-ink-soft">
                The platform that drives the agentic side of digiquant.
              </span>
            </span>
          </CtaLink>
          <dl className="m-0 grid gap-1 font-mono text-[0.72rem]">
            {DIGITHINGS.map((row) => (
              <div key={row.label} className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-3">
                <dt className="text-ink">{row.label}</dt>
                <dd className="m-0 text-ink-soft">{row.line}</dd>
              </div>
            ))}
          </dl>
        </div>

        <p className="m-0 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-[0.66rem] text-ink-mute">
          <span>also connected</span>
          {SECONDARY.map((s) => (
            <span key={s.id} className="flex items-center gap-1.5">
              <IntegrationMark id={s.id} size={14} />
              {s.name} · {s.role}
            </span>
          ))}
        </p>
        <p className="m-0 font-mono text-[0.66rem] text-ink-mute">
          This site only shows them: it places no orders and there is no live trading. The hero chart is live LuxAlgo Vela on the
          public Coinbase feed. Names and marks belong to their owners; listing one implies no affiliation.
        </p>
      </div>
    </Band>
  );
}
