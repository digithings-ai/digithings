"use client";

import { useState } from "react";

/**
 * Pipeline — a workflow visualization ported from the olympus dashboard's
 * pipeline section (frontend/olympus/components/pipeline). A left→right flow of
 * stages with a parallel fan-out group; each step carries its diagnostics
 * (wall time · tokens · model), connectors show how one feeds the next, and
 * selecting a node opens its inputs/outputs and full diagnostics. Works for
 * sequential and parallel graphs alike. Static demo data — a display template.
 */
type Status = "done" | "running" | "queued";
type PipeNode = {
  id: string;
  label: string;
  status: Status;
  ms: string;
  tokens: string;
  model: string;
  inputs: string;
  outputs: string;
  cost: string;
};
type Column = { id: string; kind: "step" | "parallel"; label?: string; nodes: PipeNode[] };

const COLUMNS: Column[] = [
  {
    id: "c1",
    kind: "step",
    nodes: [
      { id: "ingest", label: "ingest", status: "done", ms: "120ms", tokens: "—", model: "polars", inputs: "watchlist · 6 venues", outputs: "3,102 normalized bars", cost: "$0.00" },
    ],
  },
  {
    id: "c2",
    kind: "step",
    nodes: [
      { id: "research", label: "research", status: "done", ms: "2.41s", tokens: "8.2k", model: "opus", inputs: "normalized bars + macro feed", outputs: "4 candidate directions", cost: "$0.11" },
    ],
  },
  {
    id: "c3",
    kind: "parallel",
    label: "parallel · 3",
    nodes: [
      { id: "indicators", label: "indicators", status: "done", ms: "340ms", tokens: "—", model: "indicators lib", inputs: "bars + directions", outputs: "RSI · ADF · DPSD", cost: "$0.00" },
      { id: "signals", label: "signals", status: "done", ms: "210ms", tokens: "—", model: "signal gen", inputs: "indicators", outputs: "entry/exit signals", cost: "$0.00" },
      { id: "risk", label: "risk-scan", status: "done", ms: "1.10s", tokens: "3.4k", model: "haiku", inputs: "signals + exposure", outputs: "gross 0.62× · ok", cost: "$0.01" },
    ],
  },
  {
    id: "c4",
    kind: "step",
    nodes: [
      { id: "backtest", label: "backtest", status: "running", ms: "4.1s…", tokens: "—", model: "nautilus", inputs: "signals + risk verdict", outputs: "tearsheet (streaming)", cost: "$0.00" },
    ],
  },
  {
    id: "c5",
    kind: "step",
    nodes: [
      { id: "execute", label: "execute", status: "queued", ms: "—", tokens: "—", model: "kairos · gated", inputs: "passed tearsheet", outputs: "— (human gate)", cost: "—" },
    ],
  },
];

const ALL = COLUMNS.flatMap((c) => c.nodes);

export function PipelineReference() {
  const [selId, setSelId] = useState("research");
  const sel = ALL.find((n) => n.id === selId) ?? ALL[0];

  return (
    <section className="section-block" id="pipeline">
      <p className="kicker">{"// pipeline"}</p>
      <h2 className="title">Workflows, step by step.</h2>
      <p className="section-copy">
        The olympus dashboard&apos;s pipeline view, for any sequential or parallel workflow: stages
        flow left to right, a fan-out group runs in parallel, and each step carries its diagnostics
        — wall time, token usage, model. Select a node to read what fed in, what came out, and the
        full cost. Reduced to a display template here.
      </p>

      {/* Only the outer wrappers migrate to token-backed Tailwind utilities via
          the @theme bridge — the pl-summary/pl-flow/pl-colwrap/pl-col boxes.
          Their classes stay on the elements because combinators (.pl-summary >
          span) still style the children; everything inside the nodes, detail,
          io and diag grids keeps its CSS (state variants, @keyframes pulse,
          tabular-nums, media queries). bg-surface/55 emits the color-mix. */}
      <div className="pl-summary mt-[1.4rem] flex flex-wrap gap-x-[2rem] gap-y-0 rounded-[10px] border border-hair bg-surface/55 px-[1.1rem] py-[0.85rem]" role="list">
        <span role="listitem">
          <span className="pl-sum-k">wall time</span>
          <span className="pl-sum-v">8.4s</span>
        </span>
        <span role="listitem">
          <span className="pl-sum-k">tokens</span>
          <span className="pl-sum-v">11.6k</span>
        </span>
        <span role="listitem">
          <span className="pl-sum-k">steps</span>
          <span className="pl-sum-v">7</span>
        </span>
        <span role="listitem">
          <span className="pl-sum-k">cost</span>
          <span className="pl-sum-v">$0.13</span>
        </span>
        <span role="listitem">
          <span className="pl-sum-k">status</span>
          <span className="pl-sum-v pl-running">running</span>
        </span>
      </div>

      <div className="pl-flow mt-[1rem] flex items-center gap-0 overflow-x-auto pt-[0.4rem] px-[0.1rem] pb-[0.8rem]">
        {COLUMNS.map((col, i) => (
          <div key={col.id} className="pl-colwrap flex items-center shrink-0">
            <div className={`pl-col flex flex-col gap-[0.5rem]${col.kind === "parallel" ? " pl-col--par" : ""}`}>
              {col.label ? <span className="pl-col-tag">{col.label}</span> : null}
              {col.nodes.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`pl-node pl-node--${n.status}${n.id === sel.id ? " is-sel" : ""}`}
                  aria-pressed={n.id === sel.id}
                  onClick={() => setSelId(n.id)}
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
            {i < COLUMNS.length - 1 ? (
              <span className="pl-conn" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 12h15M13 6l6 6-6 6" />
                </svg>
              </span>
            ) : null}
          </div>
        ))}
      </div>

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
    </section>
  );
}
