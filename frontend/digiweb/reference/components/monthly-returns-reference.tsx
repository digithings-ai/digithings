/**
 * Returns matrix — the tearsheet period matrix: months across, years down,
 * each cell tinted by its value on the money tokens — deeper `--up` for
 * stronger gains, `--down` for losses (drawdown and volatility read all-down),
 * empty where there is no data yet — with the year column compounding the
 * total. Consumes the shared <ReturnsMatrix/> from the finance-tearsheet
 * family; the former <MonthlyReturns/> heatmap was deprecated into it (#1463)
 * — this is the monthly slice. The full family (synced SVG charts, KPI strip,
 * trade log) lives on the /tearsheet page. Static display template.
 */
import { ReturnsMatrix, TEARSHEET_DEMO } from "@digithings/web";

export function MonthlyReturnsReference() {
  return (
    <section className="section-block monthly-returns">
      <p className="kicker">{"// returns matrix"}</p>
      <h2 className="title">Every month, graded by heat.</h2>
      <p className="section-copy">
        The tearsheet period matrix: months across, years down, each cell tinted by return —
        deeper <code>--up</code> for stronger gains, <code>--down</code> for losses, empty where
        there is no data yet. Tint scales to the grid&apos;s own max-abs, figures shed decimals as
        magnitude grows (crypto-scale returns fit the cells), and the year column compounds. The
        eye reads the strategy&apos;s seasons at a glance; quarterly/annual granularity and
        drawdown/volatility metrics are one prop away — the full grammar lives on the{" "}
        <a href="/tearsheet">tearsheet page</a>.
      </p>

      <div className="mt-[1.2rem]">
        <ReturnsMatrix points={TEARSHEET_DEMO.equity} drawdown={TEARSHEET_DEMO.drawdown} period="monthly" />
      </div>
    </section>
  );
}
