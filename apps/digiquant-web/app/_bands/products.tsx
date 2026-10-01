import { Band } from "../_chrome/Band";
import { INTEGRATIONS, PRODUCT_ROWS } from "../_products";
import { ProductsScan } from "@/components/products/ProductsScan";

/** Tooling and integrations: one compact band. What the dashboard is built on and
 *  connects to, as a process pane and an integrations ledger, all text, with honest
 *  status on every row. */
export function ProductsBand() {
  return (
    <Band
      id="tooling"
      layout="split"
      tint
      status="from the repo"
      title="Tooling and integrations"
      takeaway="What sits behind the dashboard: the parts that run today, the roadmap, and the data and tools they connect to."
    >
      <ProductsScan manifest={PRODUCT_ROWS} integrations={INTEGRATIONS} />
    </Band>
  );
}
