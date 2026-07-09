/**
 * Pipeline — a workflow visualization ported from the olympus dashboard's
 * pipeline section (frontend/olympus/components/pipeline). A left→right flow of
 * stages with a parallel fan-out group; each step carries its diagnostics
 * (wall time · tokens · model), connectors show how one feeds the next, and
 * selecting a node opens its inputs/outputs and full diagnostics. Works for
 * sequential and parallel graphs alike. Static demo data — a display template.
 * Consumes the shared <Pipeline/> primitive from @digithings/web.
 */
import {
  Pipeline,
  type PipelineColumn,
  type PipelineSummaryItem,
} from "@digithings/web";

const COLUMNS: PipelineColumn[] = [
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

const SUMMARY: PipelineSummaryItem[] = [
  { label: "wall time", value: "8.4s" },
  { label: "tokens", value: "11.6k" },
  { label: "steps", value: "7" },
  { label: "cost", value: "$0.13" },
  { label: "status", value: "running", running: true },
];

export function PipelineReference() {
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

      <Pipeline
        columns={COLUMNS}
        summary={SUMMARY}
        defaultSelectedId="research"
        className="mt-[1.4rem]"
      />
    </section>
  );
}
