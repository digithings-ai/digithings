/**
 * Monthly returns — the tearsheet heatmap: months across, years down. Each cell
 * is tinted by its return, deeper up for stronger gains and down for losses,
 * empty where there's no data yet; the year column carries the YTD total in the
 * money colors. Consumes the shared <MonthlyReturns/> primitive from
 * @digithings/web with its deterministic demo grid. Static display template.
 */
import { MonthlyReturns, MONTHLY_RETURNS_DEMO } from "@digithings/web";

export function MonthlyReturnsReference() {
  return (
    <section className="section-block monthly-returns">
      <p className="kicker">{"// monthly returns"}</p>
      <h2 className="title">Every month, graded by heat.</h2>
      <p className="section-copy">
        The tearsheet heatmap: months across, years down, each cell tinted by return — deeper{" "}
        <code>--up</code> for stronger gains, <code>--down</code> for losses, empty where there is
        no data yet. The eye reads the strategy&apos;s seasons at a glance; the year column carries
        the total.
      </p>

      <MonthlyReturns rows={MONTHLY_RETURNS_DEMO} className="mt-[1.2rem]" />
    </section>
  );
}
