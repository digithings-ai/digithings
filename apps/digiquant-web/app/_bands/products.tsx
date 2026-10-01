import { Band } from "../_chrome/Band";
import { INTEGRATIONS, PRODUCT_ROWS } from "../_products";
import { ProductsScan } from "@/components/products/ProductsScan";

/** Products and integrations: one compact band. The `products` process pane and an
 *  integrations ledger, all text, with honest status on every row. */
export function ProductsBand() {
  return (
    <Band
      id="products"
      layout="split"
      status="from the repo"
      title="Products and integrations"
      takeaway="What runs today, what is on the roadmap, and the data and tools it is built on."
    >
      <ProductsScan manifest={PRODUCT_ROWS} integrations={INTEGRATIONS} />
    </Band>
  );
}
