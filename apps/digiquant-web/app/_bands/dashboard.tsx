import { Band, Slot } from "../_chrome/Band";

export function DashboardBand() {
  return (
    <Band id="dashboard" layout="center" tint title="The dashboard" takeaway="The book, the run and the results in one view.">
      <Slot height="26rem" label="Live book (paper) and dashboard walkthrough video: recording to come" />
    </Band>
  );
}
