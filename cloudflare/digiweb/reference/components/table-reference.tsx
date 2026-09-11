/**
 * Ledger table specimen — the plain Table primitive from @digithings/web,
 * live. This is the unopinionated shell: hairline rows, micro-cap header,
 * mono numerals, caption below. Sorting, virtual rows, and matrix styling
 * stay where they belong — SortableTable, TradeLogTable, PricingMatrix own
 * their grammars and do not compose this one. Numeric columns take
 * `numeric` (right + tabular figures); wide tables wrap in
 * `.ctl-table-scroll`.
 */
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@digithings/web";

const RUNS = [
  { run: "btc_slapper", bars: "3,164", cagr: "+333.10%", maxDd: "−30.50%", pf: "10.25" },
  { run: "eth_slapper", bars: "2,540", cagr: "+118.44%", maxDd: "−41.20%", pf: "4.02" },
  { run: "sol_slapper", bars: "1,902", cagr: "+96.10%", maxDd: "−52.77%", pf: "2.31" },
  { run: "btc_sdca", bars: "3,164", cagr: "+41.90%", maxDd: "−22.18%", pf: "1.82" },
];

export function TableReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// ledger table"}</p>
      <h2 className="title">Rows before opinions.</h2>
      <p className="section-copy">
        <code>Table</code> from <code>@digithings/web</code> is the plain ledger: header, rows,
        footer total, caption — nothing else. Anything with its own grammar (sortable
        leaderboards, trade logs, the returns matrix) keeps it.
      </p>

      <div className="ctl-table-scroll mt-[1.2rem]">
        <Table>
          <TableCaption>Four calibrated runs. In-sample, 1D bars, Nautilus backtest.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Run</TableHead>
              <TableHead numeric>Bars</TableHead>
              <TableHead numeric>CAGR</TableHead>
              <TableHead numeric>Max DD</TableHead>
              <TableHead numeric>PF</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {RUNS.map((r) => (
              <TableRow key={r.run}>
                <TableCell>{r.run}</TableCell>
                <TableCell numeric>{r.bars}</TableCell>
                <TableCell numeric>{r.cagr}</TableCell>
                <TableCell numeric>{r.maxDd}</TableCell>
                <TableCell numeric>{r.pf}</TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell>Mean</TableCell>
              <TableCell numeric>2,693</TableCell>
              <TableCell numeric>+147.39%</TableCell>
              <TableCell numeric>−36.66%</TableCell>
              <TableCell numeric>4.60</TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      </div>
    </section>
  );
}
