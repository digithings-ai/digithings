"use client";

import { useState } from "react";

/**
 * Pipeline — the olympus dashboard's workflow visualization promoted from the
 * design reference (effects/pipeline). Stages flow left→right, a `parallel`
 * column fans out into a dashed group, each node carries its diagnostics
 * (wall time · tokens · model), and selecting a node opens its inputs/outputs
 * and full diagnostics in the detail panel below. Works for sequential and
 * parallel graphs alike; an optional summary strip carries the run-level
 * readout. All copy and numbers arrive via props — preformatted display
 * strings, the component never formats.
 *
 * Selection is uncontrolled (`defaultSelectedId` + `onSelect`); status wears
 * the accent for `running` and fades `queued`, per the reference grammar.
 *
 * Client component (selection state). Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/effects-chrome.css";
 *                 @source "<path-to>/digiweb/web/src/components/effects-chrome";
 */
export type PipelineStatus = "done" | "running" | "queued";

export type PipelineNode = {
  id: string;
  /** Mono node name — "ingest", "backtest" … */
  label: string;
  status: PipelineStatus;
  /** Preformatted wall-time read — "2.41s", "120ms", "—". */
  ms: string;
  /** Preformatted token read — "8.2k", "—". */
  tokens: string;
  /** Model / engine chip — "opus", "nautilus", "polars" … */
  model: string;
  /** What fed in — one preformatted line. */
  inputs: string;
  /** What came out — one preformatted line. */
  outputs: string;
  /** Preformatted cost read — "$0.11", "—". */
  cost: string;
};

export type PipelineColumn = {
  id: string;
  /** `parallel` draws the dashed fan-out group around the column's nodes. */
  kind: "step" | "parallel";
  /** Tag over a parallel group — "parallel · 3". */
  label?: string;
  nodes: PipelineNode[];
};

export type PipelineSummaryItem = {
  /** Mono micro-caps key — "wall time", "cost" … */
  label: string;
  /** Preformatted value — "8.4s", "$0.13". */
  value: string;
  /** Accent the value (the live "running" read). */
  running?: boolean;
};

export type PipelineProps = {
  columns: PipelineColumn[];
  /** Optional run-level readout strip above the flow. */
  summary?: PipelineSummaryItem[];
  /** Node opened on first render — defaults to the first node. */
  defaultSelectedId?: string;
  onSelect?: (node: PipelineNode) => void;
  className?: string;
};

export function Pipeline({ columns, summary, defaultSelectedId, onSelect, className }: PipelineProps) {
  const [selId, setSelId] = useState(defaultSelectedId);
  const all = columns.flatMap((c) => c.nodes);
  const sel = all.find((n) => n.id === selId) ?? all[0];

  return (
    <div className={className}>
      {summary && summary.length > 0 ? (
        <div
          className="pl-summary flex flex-wrap gap-x-[2rem] gap-y-0 rounded-[10px] border border-hair bg-surface/55 px-[1.1rem] py-[0.85rem]"
          role="list"
        >
          {summary.map((s) => (
            <span key={s.label} role="listitem">
              <span className="pl-sum-k">{s.label}</span>
              <span className={`pl-sum-v${s.running ? " pl-running" : ""}`}>{s.value}</span>
            </span>
          ))}
        </div>
      ) : null}

      <div
        className={`pl-flow flex items-center gap-0 overflow-x-auto pt-[0.4rem] px-[0.1rem] pb-[0.8rem]${
          summary && summary.length > 0 ? " mt-[1rem]" : ""
        }`}
      >
        {columns.map((col, i) => (
          <div key={col.id} className="pl-colwrap flex items-center shrink-0">
            <div className={`pl-col flex flex-col gap-[0.5rem]${col.kind === "parallel" ? " pl-col--par" : ""}`}>
              {col.label ? <span className="pl-col-tag">{col.label}</span> : null}
              {col.nodes.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`pl-node pl-node--${n.status}${sel && n.id === sel.id ? " is-sel" : ""}`}
                  aria-pressed={sel ? n.id === sel.id : false}
                  onClick={() => {
                    setSelId(n.id);
                    onSelect?.(n);
                  }}
                >
                  <span className="pl-node-head">
                    <span className="pl-pip" aria-hidden="true" />
                    <span className="pl-node-label">{n.label}</span>
                  </span>
                  <span className="pl-node-diag">
                    <span>{n.ms}</span>
                    <span className="pl-node-tok">{n.tokens} tok</span>
                  </span>
                </button>
              ))}
            </div>
            {i < columns.length - 1 ? (
              <span className="pl-conn" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  width="18"
                  height="18"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M4 12h15M13 6l6 6-6 6" />
                </svg>
              </span>
            ) : null}
          </div>
        ))}
      </div>

      {sel ? (
        <div className="pl-detail">
          <div className="pl-detail-head">
            <span className={`pl-pip pl-pip--${sel.status}`} aria-hidden="true" />
            <span className="pl-detail-name">{sel.label}</span>
            <span className="pl-detail-model">{sel.model}</span>
            <span className={`pl-detail-status pl-detail-status--${sel.status}`}>{sel.status}</span>
          </div>
          <dl className="pl-io">
            <div>
              <dt>inputs</dt>
              <dd>{sel.inputs}</dd>
            </div>
            <div>
              <dt>outputs</dt>
              <dd>{sel.outputs}</dd>
            </div>
          </dl>
          <div className="pl-diag-grid">
            <div>
              <span className="pl-diag-k">wall time</span>
              <span className="pl-diag-v">{sel.ms}</span>
            </div>
            <div>
              <span className="pl-diag-k">tokens</span>
              <span className="pl-diag-v">{sel.tokens}</span>
            </div>
            <div>
              <span className="pl-diag-k">model</span>
              <span className="pl-diag-v">{sel.model}</span>
            </div>
            <div>
              <span className="pl-diag-k">cost</span>
              <span className="pl-diag-v">{sel.cost}</span>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
