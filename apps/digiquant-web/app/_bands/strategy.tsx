import { Band, Slot } from "../_chrome/Band";

export function StrategyBand() {
  return (
    <Band id="strategy" layout="split" flip title="Strategy development" takeaway="Describe a strategy in chat; the tools build, test and export it. Not live yet." status="in development">
      <Slot height="20rem" label="Simulation · scripted · not connected to any MCP server" />
    </Band>
  );
}
