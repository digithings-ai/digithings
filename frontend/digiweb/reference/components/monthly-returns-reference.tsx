const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const YEARS = [2022, 2023, 2024, 2025, 2026];

// Deterministic monthly returns (%) so the heatmap is stable across renders.
function grid() {
  let seed = 9973;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  return YEARS.map((year) => {
    const months = MONTHS.map((_, m) => {
      // 2026 only has data through June
      if (year === 2026 && m > 5) return null;
      return Math.round((rnd() - 0.42) * 24 * 10) / 10;
    });
    const ytd = months.reduce<number>((a, v) => a + (v ?? 0), 0);
    return { year, months, ytd: Math.round(ytd * 10) / 10 };
  });
}

const ROWS = grid();
const PEAK = 18; // % magnitude mapped to full tint

function cellStyle(v: number | null) {
  if (v === null) return undefined;
  const mag = Math.min(1, Math.abs(v) / PEAK);
  const token = v >= 0 ? "--up" : "--down";
  return {
    background: `color-mix(in srgb, var(${token}) ${Math.round(mag * 72)}%, transparent)`,
    color: mag > 0.5 ? "var(--bg)" : "var(--ink)",
  } as const;
}

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

      <div className="mr-scroll">
        <table className="mr-table">
          <thead>
            <tr>
              <th scope="col" aria-label="Year" />
              {MONTHS.map((mo) => (
                <th key={mo} scope="col">
                  {mo}
                </th>
              ))}
              <th scope="col" className="mr-ytd-head">
                Year
              </th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.year}>
                <th scope="row">{row.year}</th>
                {row.months.map((v, i) => (
                  <td key={i} style={cellStyle(v)}>
                    {v === null ? "" : v.toFixed(1)}
                  </td>
                ))}
                <td className={`mr-ytd ${row.ytd >= 0 ? "up" : "down"}`}>
                  {row.ytd >= 0 ? "+" : ""}
                  {row.ytd.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
