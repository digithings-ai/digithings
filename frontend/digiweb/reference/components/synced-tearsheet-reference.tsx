/**
 * One Lightweight Charts instance, two panes sharing a single time axis:
 * cumulative equity on top, the underwater drawdown below. The drawdown is
 * derived from the *same* walk (the primitive computes it from the equity's
 * running peak), so a dip in equity is the same bar as the red beneath it —
 * and because they live in one chart, the x-axis, crosshair and zoom are
 * synced natively (no cross-chart plumbing). Equity wears the module accent
 * (identity); drawdown wears --down (it only ever reads negative). Consumes
 * the shared <SyncedTearsheet/> primitive from @digithings/web.
 */
import { SyncedTearsheet, type TearsheetPoint } from "@digithings/web";

function generate(n: number): TearsheetPoint[] {
  let seed = 730217;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const equity: TearsheetPoint[] = [];
  let eq = 100;
  const start = new Date(Date.UTC(2022, 0, 1));
  for (let i = 0; i < n; i++) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + i * 7);
    eq = Math.max(40, eq * (1 + (rnd() - 0.44) * 0.05));
    equity.push({ time: date.toISOString().slice(0, 10), value: eq });
  }
  return equity;
}

const EQUITY = generate(210);

export function SyncedTearsheetReference() {
  return <SyncedTearsheet equity={EQUITY} />;
}
