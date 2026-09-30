import { Band, Slot } from "../_chrome/Band";

export function ProductsBand() {
  return (
    <Band id="products" layout="split" title="Products and integrations" takeaway="What runs today, what is on the roadmap, and the data and tools it is built on.">
      <Slot height="16rem" label="Compact ledger: products with status, integrations with attribution" />
    </Band>
  );
}
