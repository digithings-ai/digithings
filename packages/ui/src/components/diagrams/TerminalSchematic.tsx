"use client";

/**
 * Terminal schematic — a fully drawn monospace flow.
 *
 * Structure is on screen from the first paint: 1px boxes, dotted orthogonal
 * joins, a loop back, a legend, a numbered list, and a receipt. Motion is
 * telemetry only (a mark on the trunk, a cluster on the live bus, status
 * words, a snapping meter, a scrolling receipt). Nothing draws on.
 *
 * Styles: `@digithings/ui/styles/diagrams.css` (the `.tschem` block).
 */

import { useEffect, useState } from "react";

import { useMotionSafe } from "../../motion/primitives";

export type SchematicTone = "main" | "model" | "side" | "fallback" | "pending";

export type SchematicNode = {
  label: string;
  tone: SchematicTone;
};

/** One row. More than one node means those steps run together. */
export type SchematicRow = {
  nodes: readonly SchematicNode[];
};

export type SchematicLegend = {
  tone: SchematicTone | "ok";
  label: string;
};

export type TerminalSchematicProps = {
  title: string;
  /** Accessible name for the whole picture. */
  label: string;
  rows: readonly SchematicRow[];
  /** Why the flow returns to the top. */
  loop: string;
  notes: readonly string[];
  /** Status lines for the receipt. Presentational, not a transcript. */
  receipt: readonly string[];
  legend: readonly SchematicLegend[];
};

type BoxStatus = "running" | "ok" | "idle" | "pending" | "hold";

function rowPending(row: SchematicRow): boolean {
  return row.nodes.length > 0 && row.nodes.every((node) => node.tone === "pending");
}

function boxStatus(tone: SchematicTone, live: boolean, shipped: boolean): BoxStatus {
  if (tone === "pending") return "pending";
  if (tone === "fallback") return live ? "hold" : "idle";
  if (!shipped) return "idle";
  return live ? "running" : "ok";
}

/**
 * Dark terminal picture of one flow. Counters and the receipt are motion
 * for the picture — they are not a recorded run.
 */
export function TerminalSchematic({
  title,
  label,
  rows,
  loop,
  notes,
  receipt,
  legend,
}: TerminalSchematicProps) {
  const safe = useMotionSafe();
  const cycle = rows.flatMap((row, index) => (rowPending(row) ? [] : [index]));
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (!safe || cycle.length === 0) return;
    const timer = window.setInterval(() => {
      setPhase((current) => (current + 1) % cycle.length);
    }, 1400);
    return () => window.clearInterval(timer);
  }, [safe, cycle.length]);

  const cursor = cycle.length > 0 ? cycle[phase % cycle.length] : -1;
  const liveRow = cursor >= 0 ? rows[cursor] : undefined;
  const threads = liveRow && liveRow.nodes.length > 1 ? liveRow.nodes.length : 1;
  const hops = String(cycle.length === 0 ? 0 : phase + 1).padStart(2, "0");
  const phrase = liveRow
    ? `${liveRow.nodes.map((node) => node.label).join(" · ")} · running`
    : "idle";
  const filled = cycle.length === 0 ? 0 : ((phase + 1) / cycle.length) * 100;
  const log = receipt.length > 0 ? [...receipt, ...receipt] : [];

  return (
    <figure className="tschem" data-motion={safe ? "on" : "off"} aria-label={label}>
      <header className="tschem__title">{title}</header>
      <div className="tschem__body">
        <ul className="tschem__legend" aria-label="Legend">
          {legend.map((item) => (
            <li key={item.label}>
              <span className="tschem__swatch" data-tone={item.tone} aria-hidden="true" />
              {item.label}
            </li>
          ))}
        </ul>
        <div className="tschem__stack">
          <span className="tschem__drop" aria-hidden="true">
            ▾
          </span>
          <ol className="tschem__rows">
            {rows.map((row, index) => {
              const live = index === cursor;
              const shipped = !rowPending(row);
              const parallel = row.nodes.length > 1;
              return (
                <li key={row.nodes.map((node) => node.label).join("|")} className="tschem__step">
                  {index > 0 ? (
                    <span className="tschem__join" aria-hidden="true" />
                  ) : null}
                  <div className="tschem__row" data-live={live ? "true" : "false"}>
                    {parallel ? (
                      <div className="tschem__bus">
                        <span className="tschem__par">in parallel</span>
                        <span className="tschem__cluster" aria-hidden="true">
                          ···
                        </span>
                      </div>
                    ) : null}
                    <div className="tschem__nodes">
                      {row.nodes.map((node) => {
                        const status = boxStatus(node.tone, live, shipped);
                        return (
                          <div
                            key={node.label}
                            className="tschem__box"
                            data-tone={node.tone}
                            data-status={status}
                          >
                            <span className="tschem__name">{node.label}</span>
                            <span className="tschem__state">{status}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
          <p className="tschem__loop">
            <span aria-hidden="true">↩ </span>
            {loop}
          </p>
        </div>
        <ol className="tschem__notes" aria-label="Steps">
          {notes.map((note, index) => (
            <li key={note}>
              <span className="tschem__num">{String(index + 1).padStart(2, "0")}</span>
              <span>{note}</span>
            </li>
          ))}
        </ol>
      </div>
      {log.length > 0 ? (
        <div className="tschem__receipt" aria-label="Receipt">
          <div className="tschem__receipt-track">
            {log.map((line, index) => (
              <span key={`${line}-${index}`} aria-hidden={index >= receipt.length ? true : undefined}>
                {line}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      <footer className="tschem__foot">
        <span>
          hops <b>{hops}</b>
        </span>
        <span className="tschem__meter" aria-hidden="true">
          <span style={{ width: `${filled}%` }} />
        </span>
        <span>
          threads <b>{threads}</b>
        </span>
        <span className="tschem__phrase">{phrase}</span>
        <span>not a live run</span>
      </footer>
    </figure>
  );
}
