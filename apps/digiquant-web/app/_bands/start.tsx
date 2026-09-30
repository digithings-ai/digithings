import { Band, Slot } from "../_chrome/Band";

export function StartBand() {
  return (
    <Band id="start" title="Get started" takeaway="Clone it, run it locally, or pick a tier.">
      <Slot label="Install command, MCP command and compact pricing strip" />
    </Band>
  );
}
