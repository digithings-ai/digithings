/**
 * Drawdown plot — the underwater curve: percent below the running peak on
 * TradingView Lightweight Charts, hanging under a zero baseline in the
 * `--down` money color (it only ever reads negative). Consumes the shared
 * <DrawdownPlot/> primitive from @digithings/web with its deterministic
 * demo walk. Static display template.
 */
import { DrawdownPlot, DRAWDOWN_DEMO } from "@digithings/web";

export function DrawdownPlotReference() {
  return <DrawdownPlot data={DRAWDOWN_DEMO} />;
}
