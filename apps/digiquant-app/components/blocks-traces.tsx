"use client";

import { useState, type ComponentType } from "react";
import type {
  TraceCost,
  TraceDetail,
  TraceListItem,
  TracesList,
  TracesSpan,
} from "@/lib/api-traces";
import { useRoute } from "@/lib/use-route";
import { Block } from "./Block";
import { KpiGrid } from "./atoms";
import { DataTable, type Col } from "./DataTable";
import { Badge, Button, MetaStrip, StateBlock, type BadgeTone } from "./ui";
import { Window } from "./Window";

/**
 * digitrace Traces tab (DIG-2661, ADR-0036 section 9): list/search, span tree,
 * tokens and cost. Every figure comes from dashboard-api's `/traces` family,
 * which filters on `workspace_id` in the application layer. Nothing here
 * queries Supabase directly and nothing is estimated.
 */

const dash = "—";
const text = (v: string | null | undefined) => (v == null || v === "" ? dash : v);
const count = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? dash : Math.round(v).toLocaleString("en-US");
const usd = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? dash : `$${v < 0.01 && v > 0 ? v.toFixed(4) : v.toFixed(2)}`;
const ms = (v: number | null | undefined) => {
  if (v == null || !Number.isFinite(v) || v < 0) return dash;
  return v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`;
};

/** Local time-of-day stamp; the raw ISO stays available in the tooltip. */
const stamp = (v: string | null | undefined) => {
  if (v == null || v === "") return dash;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d+Z$/, "Z");
};

const shortId = (id: string) => (id.length <= 12 ? id : `${id.slice(0, 8)}…${id.slice(-4)}`);

const badgeTone = (s: string | null | undefined): BadgeTone => {
  const v = (s ?? "").toLowerCase();
  if (["ok", "unset", "succeeded", "success"].includes(v)) return "ok";
  if (["error", "failed", "failure"].includes(v)) return "gap";
  if (v === "running") return "live";
  return "plain";
};

const statusBadge = (s: string | null | undefined) =>
  s ? <Badge tone={badgeTone(s)}>{s}</Badge> : dash;

function SpanBranch({ span, depth }: { span: TracesSpan; depth: number }) {
  return (
    <li>
      <div className="trace-span" style={{ paddingLeft: `${depth * 14}px` }}>
        <span className="mono" title={span.span_id}>
          {text(span.name) === dash ? shortId(span.span_id) : span.name}
        </span>
        {span.kind ? <Badge tone="plain">{span.kind}</Badge> : null}
        {span.model ? <span className="mute">{span.model}</span> : null}
        <span className="num">{ms(span.duration_ms)}</span>
        <span className="num" title="tokens in / out / total">
          {count(span.input_tokens)}/{count(span.output_tokens)}/{count(span.total_tokens)}
        </span>
        <span className="num">{usd(span.cost_usd)}</span>
        {statusBadge(span.status)}
      </div>
      {span.children.length > 0 ? (
        <ul className="trace-branch">
          {span.children.map((c) => (
            <SpanBranch key={c.span_id} span={c} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** One trace: header, totals, the span tree and the scores written back to it. */
function TraceDetailPanel({ traceId }: { traceId: string }) {
  const { env, err } = useRoute<TraceDetail>(`/traces/${traceId}`);
  if (err) return <StateBlock kind="error" title="Withheld." why={`/traces/${traceId}: ${err}`} />;
  if (!env) return <p className="note mute">loading trace…</p>;
  const d = env.data;
  return (
    <div className="trace-detail">
      <MetaStrip
        items={[
          {
            label: "Trace",
            value: (
              <span className="mono" title={d.trace.trace_id}>
                {shortId(d.trace.trace_id)}
              </span>
            ),
          },
          { label: "Started", value: stamp(d.trace.started_at) },
          { label: "Service", value: text(d.trace.service_name) },
          { label: "Source", value: text(d.trace.source) },
          { label: "Status", value: statusBadge(d.trace.status) },
        ]}
      />
      <KpiGrid
        items={[
          { label: "Spans", value: count(d.span_count) },
          { label: "Tokens", value: count(d.token_total) },
          { label: "Cost", value: usd(d.cost_total_usd) },
          { label: "Scores", value: count(d.scores.length) },
        ]}
      />
      {d.spans_pending ? (
        <StateBlock
          kind="loading"
          title="Spans pending."
          why="The trace row exists and counts spans, but the index has not flushed them yet. This view refetches; nothing is estimated."
          next={[{ label: "Reload trace", onClick: () => window.location.reload() }]}
        />
      ) : d.spans.length === 0 ? (
        <StateBlock
          kind="empty"
          title="No spans indexed."
          why="The trace row is in the window but the index holds no span for it."
        />
      ) : (
        <ul className="trace-tree">
          {d.spans.map((s) => (
            <SpanBranch key={s.span_id} span={s} depth={0} />
          ))}
        </ul>
      )}
      {d.scores.length > 0 ? (
        <DataTable
          rows={d.scores}
          rowKey={(r, i) => `${r.name}:${r.span_id}:${i}`}
          cols={[
            { key: "n", label: "Score", cell: (r) => r.name },
            {
              key: "v",
              label: "Value",
              num: true,
              cell: (r) => (r.value == null ? text(r.value_text) : String(r.value)),
            },
            {
              key: "s",
              label: "Span",
              cell: (r) => (r.span_id === "" ? "trace" : shortId(r.span_id)),
            },
            { key: "src", label: "Source", cell: (r) => text(r.source) },
          ]}
        />
      ) : (
        <p className="note mute">No scores written back to this trace.</p>
      )}
    </div>
  );
}

const traceCols: Col<TraceListItem>[] = [
  {
    key: "t",
    label: "Started",
    sort: true,
    cell: (r) => <span title={r.started_at ?? undefined}>{stamp(r.started_at)}</span>,
  },
  {
    key: "id",
    label: "Trace",
    cell: (r) => (
      <span className="mono" title={r.trace_id}>
        {shortId(r.trace_id)}
      </span>
    ),
  },
  { key: "n", label: "Name", wrap: true, sort: true, cell: (r) => text(r.name) },
  { key: "svc", label: "Service", sort: true, cell: (r) => text(r.service_name) },
  { key: "d", label: "Duration", num: true, sort: true, cell: (r) => ms(r.duration_ms) },
  { key: "sp", label: "Spans", num: true, sort: true, cell: (r) => count(r.span_count) },
  { key: "s", label: "Status", cell: (r) => statusBadge(r.status) },
];

/**
 * List + search + the selected trace's span tree in one window: the selection
 * is local state, because this shell has no query-string router and a trace
 * deep link would otherwise be a second, untested navigation surface.
 */
export function TracesExploreBlock() {
  const [term, setTerm] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const route =
    query === "" ? "/traces?limit=50" : `/traces?limit=50&q=${encodeURIComponent(query)}`;
  const { env, err } = useRoute<TracesList>(route);

  return (
    <Window
      no="31"
      label="Traces · list & span tree"
      right={query === "" ? "/traces" : `/traces?q=${query}`}
    >
      <form
        className="trace-search"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(term.trim());
        }}
      >
        <label className="sr-only" htmlFor="trace-q">
          Search traces
        </label>
        <input
          id="trace-q"
          type="search"
          value={term}
          placeholder="name, service, or a 32-hex trace id"
          maxLength={120}
          onChange={(e) => setTerm(e.target.value)}
        />
        <Button primary type="submit">
          Search
        </Button>
        {query !== "" ? (
          <Button
            type="button"
            onClick={() => {
              setTerm("");
              setQuery("");
            }}
          >
            Clear
          </Button>
        ) : null}
      </form>
      {err ? (
        <StateBlock kind="error" title="Withheld." why={`${route}: ${err}`} />
      ) : !env ? (
        <p className="note mute">loading traces…</p>
      ) : env.data.traces.length === 0 ? (
        <StateBlock
          kind="empty"
          title="No traces in this window."
          why={
            query === ""
              ? "The index holds no trace for this workspace in the last 90 days."
              : `Nothing matches “${query}” in this workspace.`
          }
        />
      ) : (
        <>
          <p className="note mute">
            {count(env.data.count)} trace{env.data.count === 1 ? "" : "s"} · newest first · index
            window is 90 days
          </p>
          <DataTable
            rows={env.data.traces}
            cols={traceCols}
            rowKey={(r) => r.trace_id}
            pageSize={25}
            onRowClick={(r) => setSelected(r.trace_id)}
          />
          <p className="note mute">Select a row to open its span tree.</p>
        </>
      )}
      {selected ? (
        <section aria-label="Selected trace" className="trace-selected">
          <header className="trace-selected-bar">
            <span className="ey">
              selected / <span className="mono">{shortId(selected)}</span>
            </span>
            <Button onClick={() => setSelected(null)}>Close</Button>
          </header>
          <TraceDetailPanel traceId={selected} />
        </section>
      ) : null}
    </Window>
  );
}

/** GET /traces/cost — tokens and cost per model over the index window. */
export function TracesCostBlock() {
  return (
    <Block<TraceCost>
      no="32"
      label="Traces · tokens & cost"
      route="/traces/cost"
      asOf={(d) => d.window.until}
    >
      {(d) => (
        <>
          <KpiGrid
            items={[
              { label: "Spans", value: count(d.totals.spans) },
              { label: "Tokens", value: count(d.totals.total_tokens), note: "input + output" },
              { label: "Cost", value: usd(d.totals.cost_usd) },
              { label: "Window", value: `${text(d.window.since)} → ${text(d.window.until)}` },
            ]}
          />
          {d.by_model.length === 0 ? (
            <StateBlock
              kind="empty"
              title="No model spans in this window."
              why="No span carries a model or provider in the indexed rows."
            />
          ) : (
            <DataTable
              rows={d.by_model}
              rowKey={(r, i) => `${r.provider ?? ""}:${r.model ?? ""}:${i}`}
              cols={[
                { key: "p", label: "Provider", sort: true, cell: (r) => text(r.provider) },
                { key: "m", label: "Model", sort: true, cell: (r) => text(r.model) },
                { key: "s", label: "Spans", num: true, sort: true, cell: (r) => count(r.spans) },
                {
                  key: "i",
                  label: "In",
                  num: true,
                  sort: true,
                  cell: (r) => count(r.input_tokens),
                },
                {
                  key: "o",
                  label: "Out",
                  num: true,
                  sort: true,
                  cell: (r) => count(r.output_tokens),
                },
                {
                  key: "t",
                  label: "Total",
                  num: true,
                  sort: true,
                  cell: (r) => count(r.total_tokens),
                },
                { key: "c", label: "Cost", num: true, sort: true, cell: (r) => usd(r.cost_usd) },
              ]}
            />
          )}
          <p className="note mute">{d.cost_caveat}</p>
          {d.truncated ? (
            <p className="note mute">
              Window truncated at 5,000 spans; narrow the dates for an exact total.
            </p>
          ) : null}
        </>
      )}
    </Block>
  );
}

export type TracesBlockDef = { id: string; title: string; route: string; Component: ComponentType };
export const TRACES_BLOCKS: TracesBlockDef[] = [
  {
    id: "tr-explore",
    title: "Traces · list & span tree",
    route: "/traces",
    Component: TracesExploreBlock,
  },
  {
    id: "tr-cost",
    title: "Traces · tokens & cost",
    route: "/traces/cost",
    Component: TracesCostBlock,
  },
];
