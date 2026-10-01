import { LocalLuxalgoWorkflow } from "@/components/luxalgo/local-luxalgo-workflow";
import { Band } from "../_chrome/Band";
import { BrokerCardsPlaceholder, ChartFramePlaceholder, GloombergTerminalPlaceholder } from "../_placeholders";

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
      <div className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-3">
          <GloombergTerminalPlaceholder />
          <BrokerCardsPlaceholder />
          <ChartFramePlaceholder />
        </div>
        <LocalLuxalgoWorkflow />
        <p className="m-0 font-mono text-[0.68rem] text-ink-mute">
          The price strip under Tearsheets uses Coinbase's public price feed. Product names belong to their owners; listing
          one here implies no affiliation.
        </p>
      </div>
    </Band>
  );
}
