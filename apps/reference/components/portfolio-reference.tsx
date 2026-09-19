/**
 * Portfolio — the open-positions blotter. A mono table of every position with
 * side, size, entry, mark, and unrealized P&L in dollars and percent, plus a
 * net footer. P&L wears the money colors (teal up / red down); the side read
 * wears them too — long takes --up, short takes --down. Static data — a
 * display template, no charting engine.
 *
 * Wave 1: the side pill is the stock kit Badge (outline) with the money tone
 * as a call-site utility, per the wave-1 chip map. T6: the table itself is the
 * kit `Table` — the frame stays the plain call-site shell; numeric columns
 * take the kit's numeric treatment. Wave 4: the last controls-layer Table
 * import was re-pointed onto `@digithings/ui/ui`, and the row header is now
 * the kit `TableRowHeader` (W4-P1 closed the no-row-header gap).
 */
import { Badge } from "@digithings/ui/ui";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
} from "@digithings/ui/ui";

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
        dollars and percent, netted at the foot. Gains and losses wear the money colors — as does
        the long/short side read. Tabular numerals keep the columns honest.
      </p>

      {/* Migrated to the stock kit Badge + the kit Table. The side pill is
          `outline` with the money tone as a call-site utility (long → up,
          short → down); the P&L column keeps its per-row up/down read. The
          frame stays the plain call-site shell. */}
      <div className="mt-[1.2rem] overflow-x-auto rounded-none border border-hair bg-surface">
        <Table className="min-w-[560px]">
          <TableHeader className="border-b border-hair">
            <TableRow>
              <TableHead>instrument</TableHead>
              <TableHead>side</TableHead>
              <TableHead numeric>size</TableHead>
              <TableHead numeric>entry</TableHead>
              <TableHead numeric>mark</TableHead>
              <TableHead numeric>unrealized</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {POSITIONS.map((p) => (
              <TableRow key={p.sym}>
                <TableRowHeader className="font-normal">{p.sym}</TableRowHeader>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={p.side === "long" ? "text-up" : "text-down"}
                  >
                    {p.side}
                  </Badge>
                </TableCell>
                <TableCell numeric className="text-ink-soft">
                  {p.size}
                </TableCell>
                <TableCell numeric className="text-ink-mute">
                  {p.entry.toLocaleString()}
                </TableCell>
                <TableCell numeric className="text-ink-soft">
                  {p.mark.toLocaleString()}
                </TableCell>
                <TableCell
                  numeric
                  className={p.pnl >= 0 ? "text-up" : "text-down"}
                >
                  {money(p.pnl)}{" "}
                  <span className="text-[0.72rem]">{pctf(p.pct)}</span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableFooter className="border-t border-hair">
            <TableRow>
              <TableCell
                colSpan={5}
                className="text-start text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute"
              >
                net unrealized
              </TableCell>
              <TableCell numeric>
                <span
                  className={`text-[0.9rem] tracking-normal ${net >= 0 ? "text-up" : "text-down"}`}
                >
                  {money(net)}
                </span>
              </TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      </div>
    </section>
  );
}
