"use client";

import type { ReactNode } from "react";
import { toneClass } from "@digithings/ui";
import { useOfficialDesk } from "@/components/dashboard/use-official-desk";
import styles from "./terminal-desk.module.css";
import { bookModel, EM, figSignedPct, type DeskModel, type DrawdownRead } from "./terminal-book";

function Win({
  no,
  label,
  right,
  cell,
  children,
}: {
  no: string;
  label: string;
  right?: string;
  cell: string;
  children: ReactNode;
}) {
  return (
    <section aria-label={label} className={`${styles.cell} ${cell} flex min-w-0 flex-col bg-surface`}>
      <header className="flex items-center justify-between gap-2 border-b border-hair px-2 py-1 font-mono text-[0.62rem] text-ink-soft">
        <span className="truncate">
          {no} / {label}
        </span>
        {right ? <span className="truncate text-ink-mute">{right}</span> : null}
      </header>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </section>
  );
}

function Kpis({ model }: { model: DeskModel }) {
  return (
    <dl className="m-0 grid grid-cols-2">
      {model.kpis.map((k) => (
        <div key={k.label} className="border-b border-e border-hair px-2 py-2">
          <dt className="font-mono text-[0.6rem] text-ink-mute">{k.label}</dt>
          <dd className="m-0 mt-1 font-mono text-[0.95rem] tabular-nums text-ink">{k.value}</dd>
          <dd className="m-0 mt-1 font-mono text-[0.6rem] text-ink-mute">{k.sub}</dd>
        </div>
      ))}
    </dl>
  );
}

function Table({
  columns,
  rows,
  empty,
}: {
  columns: string[];
  rows: ReactNode;
  empty?: string;
}) {
  return (
    <table className="w-full border-collapse font-mono text-[0.66rem]">
      <thead>
        <tr className="text-ink-mute">
          {columns.map((c) => (
            <th key={c} className="sticky top-0 bg-surface-2 px-2 py-1 text-start font-normal">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {empty ? (
          <tr>
            <td colSpan={columns.length} className="px-2 py-2 text-ink-mute">
              {empty}
            </td>
          </tr>
        ) : (
          rows
        )}
      </tbody>
    </table>
  );
}

function NavLine({ points }: { points: { nav: number }[] }) {
  if (points.length < 2) return <p className="m-0 px-2 py-2 font-mono text-[0.66rem] text-ink-mute">{EM}</p>;
  const vals = points.map((p) => p.nav);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = hi - lo || 1;
  const d = vals
    .map((v, i) => {
      const x = (i / (vals.length - 1)) * 100;
      const y = 8 + (1 - (v - lo) / span) * 84;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full min-h-[6rem] w-full text-ink" role="img" aria-label="NAV index">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.25" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function DrawdownBody({ d }: { d: DrawdownRead }) {
  return (
    <dl className="m-0 grid gap-2 px-2 py-2 font-mono text-[0.66rem]">
      <div>
        <dt className="text-ink-mute">Max</dt>
        <dd className={`m-0 tabular-nums ${toneClass(d.maxPct)}`}>{figSignedPct(d.maxPct)}</dd>
      </div>
      <div>
        <dt className="text-ink-mute">Current</dt>
        <dd className={`m-0 tabular-nums ${toneClass(d.currentPct)}`}>{figSignedPct(d.currentPct)}</dd>
      </div>
      <div>
        <dt className="text-ink-mute">Peak</dt>
        <dd className="m-0 text-ink-soft">{d.peakDate ?? EM}</dd>
      </div>
      <div>
        <dt className="text-ink-mute">Trough</dt>
        <dd className="m-0 text-ink-soft">{d.troughDate ?? EM}</dd>
      </div>
    </dl>
  );
}

export function DeskView({ model }: { model: DeskModel }) {
  return (
    <div className="border border-hair bg-surface font-mono text-ink">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hair px-2 py-1 text-[0.62rem] text-ink-mute">
        <span>digiquant · portfolio · 12×12 · paper</span>
        <span>{model.asOf ? `as of ${model.asOf}` : model.reason ?? `as of ${EM}`}</span>
      </div>
      <div className={styles.desk}>
        <Win no="01" label="Book" right="paper, not money" cell={styles.book}>
          <Kpis model={model} />
          {model.reason ? <p className="m-0 px-2 py-2 text-[0.62rem] leading-[1.45] text-ink-mute">{model.reason}</p> : null}
        </Win>
        <Win no="02" label="Sleeves" cell={styles.sleeves}>
          <Table
            columns={["Sleeve", "Names", "Weight"]}
            empty={model.sleeves.length === 0 ? "no sleeves on this read" : undefined}
            rows={model.sleeves.map((s) => (
              <tr key={s.sleeve} className="border-t border-hair">
                <td className="px-2 py-1">{s.sleeve}</td>
                <td className="px-2 py-1 tabular-nums">{s.names}</td>
                <td className="px-2 py-1 tabular-nums">{s.weight}</td>
              </tr>
            ))}
          />
        </Win>
        <Win no="03" label="Movers" cell={styles.movers}>
          <Table
            columns={["Ticker", "Mark", "Day"]}
            empty={model.movers.length === 0 ? "no day return on this read" : undefined}
            rows={model.movers.map((m) => (
              <tr key={m.ticker} className="border-t border-hair">
                <td className="px-2 py-1">{m.ticker}</td>
                <td className="px-2 py-1 tabular-nums">{m.mark}</td>
                <td className={`px-2 py-1 tabular-nums ${toneClass(m.dayN)}`}>{m.day}</td>
              </tr>
            ))}
          />
        </Win>
        <Win no="04" label="Holdings" cell={styles.holdings}>
          <Table
            columns={["Ticker", "Name", "Weight", "Shares", "Mark", "Day"]}
            empty={model.holdings.length === 0 ? "no positions on this read" : undefined}
            rows={model.holdings.map((h) => (
              <tr key={h.ticker} className="border-t border-hair">
                <td className="px-2 py-1">{h.ticker}</td>
                <td className="max-w-[14rem] truncate px-2 py-1">{h.name}</td>
                <td className="px-2 py-1 tabular-nums">{h.weight}</td>
                <td className="px-2 py-1 tabular-nums text-ink-mute">{h.shares}</td>
                <td className="px-2 py-1 tabular-nums">{h.mark}</td>
                <td className={`px-2 py-1 tabular-nums ${toneClass(h.dayN)}`}>{h.day}</td>
              </tr>
            ))}
          />
        </Win>
        <Win no="05" label="NAV" right={model.navPoints.length ? "index" : EM} cell={styles.nav}>
          <NavLine points={model.navPoints} />
          <p className="m-0 flex justify-between border-t border-hair px-2 py-1 text-[0.6rem] text-ink-mute">
            <span>{model.navStart}</span>
            <span>{model.navEnd}</span>
          </p>
        </Win>
        <Win no="06" label="Drawdown" cell={styles.drawdown}>
          <DrawdownBody d={model.drawdown} />
        </Win>
      </div>
    </div>
  );
}

/** Portfolio windows from the official API. Stub, withheld, and missing figures stay an em dash. */
export function TerminalDesk() {
  const live = useOfficialDesk();
  return <DeskView model={bookModel(live)} />;
}
