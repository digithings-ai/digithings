import { Band } from "../_chrome/Band";
import { INTEGRATIONS, PRODUCT_ROWS } from "../_products";
import { BrokerCardsPlaceholder, GloombergTerminalPlaceholder } from "../_placeholders";
import { ProductsScan } from "@/components/products/ProductsScan";

/** Tooling: two placeholders on an equal two-column grid (data terminal teaser,
 *  broker cards), then the process pane and the integrations ledger. All text,
 *  honest status on every row. */
export function ProductsBand() {
  return (
    <Band
      id="tooling"
      tint
      status="from the repo"
      title="Tooling and integrations"
      takeaway="What the dashboard is built on and connects to. Each row says whether it runs today or is on the roadmap."
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-2">
          <GloombergTerminalPlaceholder />
          <BrokerCardsPlaceholder />
        </div>
        <ProductsScan manifest={PRODUCT_ROWS} integrations={INTEGRATIONS} />
      </div>
    </Band>
  );
}
