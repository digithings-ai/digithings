/**
 * Portfolio workspace — the page-level grammar for a research-driven book: a
 * restrained command band establishes exposure, then a full-width position
 * ledger carries only the information needed to monitor and follow a holding.
 * Static data, token-only dress.
 *
 * Wave 1 (T6): the ledger is the controls-layer kit `Table`
 * (`@digithings/web`); the `.pw-table*` dress is deleted from finance.css.
 * The command band keeps its `.pw-command*` grammar.
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@digithings/web";

const POSITIONS = [
  { ticker: "XLE", category: "energy", weight: "17.2%", targetWeight: "18.0%", stop: "−8%", priceTarget: "+15%" },
  { ticker: "XLF", category: "financials", weight: "17.2%", targetWeight: "16.0%", stop: "−6%", priceTarget: "+12%" },
  { ticker: "UUP", category: "fx", weight: "15.2%", targetWeight: "15.0%", stop: "−5%", priceTarget: "+9%" },
  { ticker: "XLRE", category: "real estate", weight: "12.9%", targetWeight: "11.0%", stop: "−7%", priceTarget: "+11%" },
  { ticker: "XLV", category: "healthcare", weight: "12.9%", targetWeight: "14.0%", stop: "−6%", priceTarget: "+10%" },
];

export function PortfolioWorkspaceReference() {
  return (
    <section className="section-block pw-ref" id="portfolio-workspace">
      <p className="kicker">{"// portfolio workspace"}</p>
      <h2 className="title">The book reads like a decision surface.</h2>
      <p className="section-copy">
        The canonical page composition for an active portfolio: one exposure figure, the position
        count, and a ledger that keeps allocation, risk, and provenance easy to scan.
      </p>

      <div className="pw-frame">
        <header className="pw-command">
          <div className="pw-command__identity">
            <span className="pw-label">invested</span>
            <strong>84.8%</strong>
          </div>
          <dl className="pw-command__metrics">
            <div>
              <dt>positions</dt>
              <dd>{POSITIONS.length}</dd>
            </div>
          </dl>
          <div className="pw-command__stamp">
            <span>as of</span>
            <strong>19 JUL 2026</strong>
          </div>
        </header>

        <section className="pw-ledger" aria-labelledby="pw-ledger-title">
          <div className="pw-section-head">
            <div>
              <span className="pw-label">active allocation</span>
              <h3 id="pw-ledger-title">Positions</h3>
            </div>
            <span className="pw-section-meta">allocation · risk · dossier</span>
          </div>

          <div className="ctl-table-scroll">
            <Table>
              <TableHeader className="border-b border-hair">
                <TableRow>
                  <TableHead>ticker</TableHead>
                  <TableHead>category</TableHead>
                  <TableHead numeric>current / target</TableHead>
                  <TableHead numeric>stop / target</TableHead>
                  <TableHead>follow</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {POSITIONS.map((position) => (
                  <TableRow key={position.ticker}>
                    <TableCell>
                      <strong>{position.ticker}</strong>
                    </TableCell>
                    <TableCell className="text-ink-mute">{position.category}</TableCell>
                    <TableCell numeric>
                      <span className="pw-allocation">
                        <strong>{position.weight}</strong>
                        <small>target {position.targetWeight}</small>
                      </span>
                    </TableCell>
                    <TableCell numeric>
                      {position.stop} / {position.priceTarget}
                    </TableCell>
                    <TableCell>
                      <span className="pw-follow">dossier</span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      </div>
    </section>
  );
}
