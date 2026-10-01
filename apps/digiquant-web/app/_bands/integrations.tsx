import { IntegrationMark, type IntegrationId } from "@/components/integrations/marks";
import { LocalLuxalgoWorkflow } from "@/components/luxalgo/local-luxalgo-workflow";
import { Band } from "../_chrome/Band";
import { BrokerCardsPlaceholder, ChartFramePlaceholder, GloombergTerminalPlaceholder } from "../_placeholders";

const PARTNERS: { id: IntegrationId; name: string; role: string }[] = [
  { id: "gloomberb", name: "Gloomberb", role: "market data" },
  { id: "luxalgo", name: "LuxAlgo", role: "charts" },
  { id: "coinbase", name: "Coinbase", role: "public price feed" },
  { id: "alpaca", name: "Alpaca", role: "broker" },
  { id: "ibkr", name: "Interactive Brokers", role: "broker" },
];

/** Integrations: the only band that names data partners, chart embeds or brokers.
 *  Three placeholders on one equal row, then the LuxAlgo demo. Showcase only. */
export function IntegrationsBand() {
  return (
    <Band
      id="integrations"
      status="showcase only"
      title="Integrations"
      takeaway="The data, charts and brokers that connect to the dashboard. This site only shows them: it places no orders and there is no live trading."
    >
      <div className="flex flex-col gap-3">
        <ul aria-label="Integrated services" className="m-0 flex list-none flex-wrap gap-x-6 gap-y-2 border border-hair px-3 py-2">
          {PARTNERS.map((p) => (
            <li key={p.id} className="flex items-center gap-2 font-mono text-[0.78rem] text-ink-soft">
              <IntegrationMark id={p.id} size={18} />
              <span className="text-ink">{p.name}</span>
              <span className="text-[0.68rem] text-ink-mute">{p.role}</span>
            </li>
          ))}
        </ul>
        <div className="grid gap-4 md:grid-cols-3">
          <GloombergTerminalPlaceholder />
          <BrokerCardsPlaceholder />
          <ChartFramePlaceholder />
        </div>
        <LocalLuxalgoWorkflow />
        <p className="m-0 font-mono text-[0.68rem] text-ink-mute">
          The price strip under Tearsheets and the hero chart read the public Coinbase price feed. Names and marks belong to
          their owners; listing one here implies no affiliation.
        </p>
      </div>
    </Band>
  );
}
