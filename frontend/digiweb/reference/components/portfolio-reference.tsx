/**
 * Portfolio — the open-positions blotter. A mono table of every position with
 * side, size, entry, mark, and unrealized P&L in dollars and percent, plus a
 * net footer. P&L wears the money colors (teal up / red down); side is neutral.
 * Static data — a display template, no charting engine.
 */
type Position = {
  sym: string;
  side: "long" | "short";
  size: string;
  entry: number;
  mark: number;
  pnl: number;
  pct: number;
};

const POSITIONS: Position[] = [
  { sym: "BTC-PERP", side: "long", size: "1.20", entry: 58200, mark: 63410, pnl: 6252, pct: 8.95 },
  { sym: "ETH-PERP", side: "long", size: "8.00", entry: 2940, mark: 3088, pnl: 1184, pct: 5.03 },
  { sym: "SOL-PERP", side: "short", size: "140", entry: 151.0, mark: 142.6, pnl: 1176, pct: 5.56 },
  { sym: "NVDA", side: "long", size: "300", entry: 118.2, mark: 121.44, pnl: 972, pct: 2.74 },
  { sym: "AAPL", side: "long", size: "200", entry: 233.0, mark: 229.87, pnl: -626, pct: -1.34 },
];

const money = (n: number) =>
  `${n < 0 ? "−" : "+"}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const pctf = (n: number) => `${n < 0 ? "−" : "+"}${Math.abs(n).toFixed(2)}%`;

export function PortfolioReference() {
  const net = POSITIONS.reduce((s, p) => s + p.pnl, 0);

  return (
    <section className="section-block" id="portfolio">
      <p className="kicker">{"// portfolio"}</p>
      <h2 className="title">Every position, marked to market.</h2>
      <p className="section-copy">
        The open-positions blotter: side, size, entry, and live mark with unrealized P&amp;L in
        dollars and percent, netted at the foot. Gains and losses wear the money colors; side stays
        neutral. Tabular numerals keep the columns honest.
      </p>

      {/* Migrated to token-backed utilities. The .pos-side pill group stays in
          finance.css (its --short border is a two-color ink+hair mix). Money
          colors (text-up/text-down) are applied per-row on the unrealized P&L. */}
      <div className="mt-[1.2rem] overflow-x-auto rounded-[12px] border border-hair bg-surface">
        <table className="w-full min-w-[560px] border-collapse font-mono text-[0.82rem] [font-variant-numeric:tabular-nums]">
          <thead>
            <tr>
              {(
                [
                  ["instrument", "text-left"],
                  ["side", ""],
                  ["size", "text-right"],
                  ["entry", "text-right"],
                  ["mark", "text-right"],
                  ["unrealized", "text-right"],
                ] as const
              ).map(([label, align]) => (
                <th
                  key={label}
                  className={`border-b border-hair px-4 py-[0.7rem] text-[0.58rem] font-normal uppercase tracking-[0.1em] text-ink-mute ${align}`}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {POSITIONS.map((p) => (
              <tr key={p.sym}>
                <td className="border-b border-hair/55 px-4 py-[0.62rem] text-left text-ink">
                  {p.sym}
                </td>
                <td className="border-b border-hair/55 px-4 py-[0.62rem] text-ink-soft">
                  <span className={`pos-side pos-side--${p.side}`}>{p.side}</span>
                </td>
                <td className="border-b border-hair/55 px-4 py-[0.62rem] text-right text-ink-soft">
                  {p.size}
                </td>
                <td className="border-b border-hair/55 px-4 py-[0.62rem] text-right text-ink-mute">
                  {p.entry.toLocaleString()}
                </td>
                <td className="border-b border-hair/55 px-4 py-[0.62rem] text-right text-ink-soft">
                  {p.mark.toLocaleString()}
                </td>
                <td
                  className={`border-b border-hair/55 px-4 py-[0.62rem] text-right ${
                    p.pnl >= 0 ? "text-up" : "text-down"
                  }`}
                >
                  {money(p.pnl)}{" "}
                  <span className="text-[0.72rem] opacity-75">{pctf(p.pct)}</span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td
                className="border-t border-hair px-4 py-[0.8rem] text-left text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
                colSpan={5}
              >
                net unrealized
              </td>
              <td className="border-t border-hair px-4 py-[0.8rem] text-right">
                <span
                  className={`text-[0.9rem] tracking-normal ${net >= 0 ? "text-up" : "text-down"}`}
                >
                  {money(net)}
                </span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}
