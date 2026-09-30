import { Band, Slot } from "../_chrome/Band";

export function TopBand() {
  return (
    <Band
      id="top"
      as="h1"
      title="A quant research desk in a glass box you own."
      takeaway="Research runs daily, portfolio sizes the risk, and every run writes a decision log under its own run id. Open-source and self-hosted."
    >
      <Slot label="Hero: command, CTAs and counters land in the vertical slice" />
    </Band>
  );
}
