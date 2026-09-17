/**
 * Stacking panels — the second between-sections transition mined from
 * revolut.com. Each panel pins in turn and the next slides up over it (rounded
 * top + shadow give the layered seam); as a panel is covered it scales back and
 * dims. The "covered" amount keys off the *next* panel's approach to the pin
 * line — not the panel's own view progress — so it's driven by a manual
 * scroll handler writing to refs (same pattern as ResearchPipeline / the
 * zoom-morph), which also keeps it verifiable. Reduced motion: a plain stack.
 * Consumes the shared <StackingPanels/> primitive from @digithings/web.
 */
import { StackingPanels as StackingPanelsStack, type StackingPanel } from "@digithings/web";

const PANELS: StackingPanel[] = [
  { tag: "01", title: "Ingest", body: "Free macro and market data, pulled and normalized into one store." },
  { tag: "02", title: "Backtest", body: "Replay on a NautilusTrader core — full trade ledger, one tearsheet." },
  { tag: "03", title: "Execute", body: "Promote up the ladder to live — every rung of it a human gate." },
];

export function StackingPanels() {
  return <StackingPanelsStack panels={PANELS} className="mt-[1.6rem]" />;
}
