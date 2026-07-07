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

      <div className="pos-scroll">
        <table className="pos-table">
          <thead>
            <tr>
              <th className="pos-l">instrument</th>
              <th>side</th>
              <th className="pos-r">size</th>
              <th className="pos-r">entry</th>
              <th className="pos-r">mark</th>
              <th className="pos-r">unrealized</th>
            </tr>
          </thead>
          <tbody>
            {POSITIONS.map((p) => (
              <tr key={p.sym}>
                <td className="pos-l pos-sym">{p.sym}</td>
                <td>
                  <span className={`pos-side pos-side--${p.side}`}>{p.side}</span>
                </td>
                <td className="pos-r">{p.size}</td>
                <td className="pos-r pos-mute">{p.entry.toLocaleString()}</td>
                <td className="pos-r">{p.mark.toLocaleString()}</td>
                <td className="pos-r">
                  <span className={p.pnl >= 0 ? "up" : "down"}>
                    {money(p.pnl)} <span className="pos-pct">{pctf(p.pct)}</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className="pos-l" colSpan={5}>
                net unrealized
              </td>
              <td className="pos-r">
                <span className={net >= 0 ? "up" : "down"}>{money(net)}</span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}
