/**
 * Dashboard workspace — the page-level composition for dense operational and
 * research surfaces: one command band establishes the primary state, compact
 * metrics add context, and a flat hairline ledger carries the working detail.
 * Static data, token-only dress.
 *
 * Wave 1 (T6): the ledger is the controls-layer kit `Table`
 * (`@digithings/web`), and the whole component's `dw-*` grammar — which had
 * no CSS owner anywhere in the app (every `dw-*` token was dead at the call
 * site, the `.dw-table` ledger included) — is rewritten with token-backed
 * utilities that mirror the styled `.pw-*` sibling on the same page family.
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@digithings/web";

const DECISIONS = [
  {
    subject: "USD strength",
    decision: "Maintain long-dollar expression",
    state: "monitor",
    owner: "Portfolio",
    impact: "+2.7%",
    tone: "up",
    updated: "09:42",
  },
  {
    subject: "Advanced materials",
    decision: "Add only after demand confirmation",
    state: "active view",
    owner: "Research",
    impact: "+0.4%",
    tone: "up",
    updated: "08:15",
  },
  {
    subject: "Real estate duration",
    decision: "Hold below target allocation",
    state: "watch",
    owner: "Portfolio",
    impact: "−0.9%",
    tone: "down",
    updated: "07:50",
  },
] as const;

export function DashboardWorkspaceReference() {
  return (
    <section className="section-block" id="dashboard-workspace">
      <p className="kicker">{"// dashboard workspace"}</p>
      <h2 className="title">One state, then the decisions behind it.</h2>
      <p className="section-copy">
        The canonical page composition for a working dashboard: a restrained command band names
        the primary state, a small metric group adds context, and a full-width ledger makes the
        underlying decisions easy to scan without stacking decorative cards.
      </p>

      <div className="mt-[1.4rem] border-y border-hair bg-surface/80">
        <header className="grid grid-cols-[minmax(14rem,1fr)_minmax(9rem,0.55fr)_auto] border-b border-hair max-[900px]:grid-cols-[1fr_auto] max-[640px]:grid-cols-1">
          <div className="flex flex-col justify-center gap-[0.3rem] border-r border-hair p-[1.25rem_1.4rem] max-[640px]:border-r-0">
            <span className="font-mono text-[0.62rem] font-medium uppercase leading-[1.3] tracking-[0.1em] text-ink-mute">
              invested
            </span>
            <strong className="font-mono text-[clamp(2rem,4vw,3.8rem)] font-medium leading-none">
              84.8%
            </strong>
            <span className="font-mono text-[0.72rem]">selective risk-on</span>
          </div>

          <dl className="m-0 grid grid-cols-[minmax(0,1fr)] max-[900px]:col-span-full max-[900px]:row-start-2 max-[900px]:border-t max-[900px]:border-hair max-[640px]:col-span-1 max-[640px]:row-start-2">
            <div className="flex min-w-0 flex-col justify-center gap-[0.45rem] border-r border-hair p-4">
              <dt className="font-mono text-[0.62rem] font-medium uppercase leading-[1.3] tracking-[0.1em] text-ink-mute">
                positions
              </dt>
              <dd className="m-0 font-mono text-[1.05rem] text-ink [font-variant-numeric:tabular-nums]">
                11
              </dd>
            </div>
            <div className="flex min-w-0 flex-col justify-center gap-[0.45rem] border-r border-hair p-4">
              <dt className="font-mono text-[0.62rem] font-medium uppercase leading-[1.3] tracking-[0.1em] text-ink-mute">
                active views
              </dt>
              <dd className="m-0 font-mono text-[1.05rem] text-ink [font-variant-numeric:tabular-nums]">
                2
              </dd>
            </div>
          </dl>

          <div className="flex min-w-[9rem] flex-col items-end justify-center gap-[0.3rem] p-[1.25rem_1.4rem] text-right font-mono text-[0.65rem] tracking-[0.08em] text-ink-mute max-[900px]:col-start-2 max-[900px]:row-start-1 max-[640px]:col-start-1 max-[640px]:row-start-3 max-[640px]:min-w-0 max-[640px]:border-t max-[640px]:border-hair">
            <span>as of</span>
            <strong className="font-medium text-accent">21 JUL 2026</strong>
          </div>
        </header>

        <section className="min-w-0" aria-labelledby="dw-ledger-title">
          <div className="flex items-end justify-between gap-4 px-[1.4rem] pb-4 pt-[1.25rem] max-[640px]:flex-col max-[640px]:items-start">
            <div>
              <span className="font-mono text-[0.62rem] font-medium uppercase leading-[1.3] tracking-[0.1em] text-ink-mute">
                decision monitor
              </span>
              <h3
                id="dw-ledger-title"
                className="mt-[0.35rem] font-display text-[clamp(1.45rem,3vw,2.3rem)] font-medium"
              >
                Current calls
              </h3>
            </div>
            <span className="font-mono text-[0.62rem] text-ink-mute">
              state · ownership · impact · provenance
            </span>
          </div>

          <div className="ctl-table-scroll">
            <Table>
              <TableHeader className="border-b border-hair">
                <TableRow>
                  <TableHead>subject</TableHead>
                  <TableHead>decision</TableHead>
                  <TableHead>state</TableHead>
                  <TableHead>owner</TableHead>
                  <TableHead numeric>return</TableHead>
                  <TableHead numeric>updated</TableHead>
                  <TableHead>follow</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {DECISIONS.map((item) => (
                  <TableRow key={item.subject}>
                    <TableCell>
                      <strong>{item.subject}</strong>
                    </TableCell>
                    <TableCell>{item.decision}</TableCell>
                    <TableCell>
                      <span className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
                        {item.state}
                      </span>
                    </TableCell>
                    <TableCell>{item.owner}</TableCell>
                    <TableCell
                      numeric
                      className={item.tone === "up" ? "text-up" : "text-down"}
                    >
                      {item.impact}
                    </TableCell>
                    <TableCell numeric>{item.updated}</TableCell>
                    <TableCell>
                      <span className="whitespace-nowrap font-mono text-[0.7rem] text-ink-mute">
                        brief · dossier
                      </span>
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
