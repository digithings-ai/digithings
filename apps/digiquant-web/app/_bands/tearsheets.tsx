import { Band, Slot } from "../_chrome/Band";

export function TearsheetsBand() {
  return (
    <Band id="tearsheets" title="Tearsheets" takeaway="Backtest results per strategy. In-sample and illustrative, labelled as such.">
      <Slot height="18rem" label="Snap-scroll card rail of tearsheet cards" />
    </Band>
  );
}
