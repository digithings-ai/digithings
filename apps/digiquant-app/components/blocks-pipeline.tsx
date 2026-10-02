'use client';

import { useEffect, useState, type ComponentType, type ReactNode } from 'react';
import { dqGet, type Envelope } from '@/lib/dq-api';
import type {
  ArtifactLedger, CallTrace, DeployDraft, DeployFlow, NodeDocument, PipelineGraph, PipelineHealth, RunNarrative,
  StrategiesSummary, StrategyCatalog, StrategyDeployments, StrategyOverview, StrategyParameters, StrategyPerformance, StrategyRuns, StrategyTargets,
} from '@/lib/api-pipeline';
import { Block } from './Block';
import { KpiGrid } from './atoms';
import { LineChart } from './charts';
import { DataTable } from './DataTable';
import { Drawer } from './Drawer';
import { Badge, KvList, MetaStrip, Prose, SoonBar, StateBlock, type BadgeTone } from './ui';
import { Field } from './ui-form';
import { FlowGraph, Stepper, type FlowNodeData } from './ui-flow';

const dash = '—';
const text = (v: string | null | undefined) => (v == null || v === '' ? dash : v);
const count = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? dash : v.toLocaleString('en-US'));
const compact = (v: number | null | undefined) => {
  if (v == null || !Number.isFinite(v)) return dash;
  const a = Math.abs(v);
  return a >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : a >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : String(v);
};
const usd = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? dash : `$${v.toFixed(2)}`);
const duration = (s: number | null | undefined) => {
  if (s == null || !Number.isFinite(s) || s < 0) return dash;
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return m ? `${m} m ${String(r).padStart(2, '0')} s` : `${r} s`;
};
const paras = (a: string[] | null | undefined) => (Array.isArray(a) ? a.filter((p) => typeof p === 'string' && p) : []);
const withheld = (what: string) => <StateBlock kind="empty" title="Withheld." why={`${what} is not in the response yet; nothing is estimated.`} />;

const badgeTone = (s: string | null | undefined): BadgeTone => {
  const v = (s ?? '').toLowerCase();
  if (['ok', 'succeeded', 'active', 'done'].includes(v)) return 'ok';
  if (['wip', 'coming soon', 'soon', 'mock'].includes(v)) return 'wip';
  if (['not_persisted', 'not persisted', 'gap', 'failed'].includes(v)) return 'gap';
  if (v === 'unavailable') return 'unavailable';
  if (v === 'live') return 'live';
  return 'plain';
};
const statusBadge = (s: string | null | undefined) => (s ? <Badge tone={badgeTone(s)}>{s.replace(/_/g, ' ')}</Badge> : dash);

const soon = (n: { tag: 'soon' | 'wip'; text: string } | null | undefined): ReactNode => (n?.text ? <SoonBar tag={n.tag === 'soon' ? 'soon' : 'wip'}>{n.text}</SoonBar> : null);

/* ---------------- Pipeline ---------------- */

/** GET /pipeline/runs/latest/health — run header + run health strip. A full YYYY-MM-DD selects that run. */
export function PlRunHealthBlock() {
  const [date, setDate] = useState('');
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(date);
  const route = valid ? `/pipeline/runs/latest/health?date=${date}` : '/pipeline/runs/latest/health';
  return (
    <Block<PipelineHealth> no="20" label="Run health" route={route} asOf={(d) => d.run_date}>
      {(d) => (
        <>
          <Field label="Run date" value={date} placeholder="YYYY-MM-DD" hint={date && !valid ? 'use YYYY-MM-DD, or leave blank for the latest run' : 'blank is the latest run'} onChange={(e) => setDate(e.target.value)} />
          <MetaStrip items={[
            { label: 'Run', value: text(d.run_date) },
            { label: 'Type', value: text(d.run_type) },
            { label: 'Status', value: text(d.status) },
            { label: 'Config', value: text(d.config) },
            { label: 'Posture', value: text(d.posture) },
          ]} />
          <KpiGrid items={[
            { label: 'Nodes ok', value: count(d.nodes?.ok) },
            { label: 'Carried', value: count(d.nodes?.carried) },
            { label: 'Failed', value: count(d.nodes?.failed), tone: d.nodes?.failed ? 'neg' : undefined },
            { label: 'Calls', value: count(d.calls) },
            { label: 'Tokens in', value: compact(d.tokens_in) },
            { label: 'Tokens out', value: compact(d.tokens_out) },
            { label: 'Cost', value: usd(d.cost_usd) },
          ]} />
          {d.inputs_calls && d.inputs_calls.persisted !== true && d.inputs_calls.note ? (
            <StateBlock kind="empty" title="Inputs calls are not persisted." why={d.inputs_calls.note} />
          ) : null}
        </>
      )}
    </Block>
  );
}

const flowState = (s: string | null | undefined): FlowNodeData['state'] =>
  s === 'ok' || s === 'running' || s === 'failed' || s === 'idle' ? s : s === 'carried' || s === 'skipped' ? 'skipped' : 'idle';

/** GET /pipeline/runs/latest/graph — inputs to learning. TODO: node selection feeding pl-node-document needs shared selection state; graph is read-only for now. */
export function PlCanvasBlock() {
  return (
    <Block<PipelineGraph> no="21" label="Canvas · inputs to learning" route="/pipeline/runs/latest/graph" asOf={(d) => d.run_date}>
      {(d) => {
        const nodes: FlowNodeData[] = (Array.isArray(d.nodes) ? d.nodes : []).map((n) => ({
          id: n.id,
          label: n.label,
          col: Number.isFinite(n.col) ? n.col : 0,
          state: flowState(n.state),
          meta: [n.stage, n.state].filter(Boolean).join(' · ') || undefined,
          to: Array.isArray(n.to) ? n.to : undefined,
        }));
        return nodes.length ? <FlowGraph nodes={nodes} selected={d.selected_node} /> : withheld('pipeline graph');
      }}
    </Block>
  );
}

/** GET /pipeline/runs/latest/nodes/selected/document — the selected node's document. */
export function PlNodeDocumentBlock() {
  return (
    <Block<NodeDocument> no="22" label="Node document" route="/pipeline/runs/latest/nodes/selected/document" asOf={(d) => d.run_date}>
      {(d) => {
        const ps = paras(d.paragraphs);
        return d.title || ps.length ? (
          <Prose lead={d.title ?? undefined}>
            {ps.map((p, i) => <p key={i}>{p}</p>)}
            {d.note ? <p className="pl-note">{d.note}</p> : null}
          </Prose>
        ) : withheld('node document');
      }}
    </Block>
  );
}

/** GET /pipeline/runs/latest/narrative — run /why narrative. */
export function PlNarrativeBlock() {
  return (
    <Block<RunNarrative> no="23" label="Run narrative" route="/pipeline/runs/latest/narrative" asOf={(d) => d.run_date}>
      {(d) => {
        const ps = paras(d.paragraphs);
        return d.heading || ps.length ? (
          <Prose lead={d.heading ?? undefined}>{ps.map((p, i) => <p key={i}>{p}</p>)}</Prose>
        ) : withheld('narrative');
      }}
    </Block>
  );
}

/** GET /pipeline/runs/latest/trace — calls and duration per node. The bar is this row against the longest duration in the response. */
export function PlCallTraceBlock() {
  return (
    <Block<CallTrace> no="24" label="Call trace" route="/pipeline/runs/latest/trace">
      {(d) => {
        const max = d.rows.reduce((m, r) => (r.duration_s != null && r.duration_s > m ? r.duration_s : m), 0);
        return (
        <DataTable
          rows={d.rows}
          rowKey={(r, i) => `${r.node}:${i}`}
          empty="no calls traced"
          cols={[
            { key: 'n', label: 'Node', wrap: true, cell: (r) => r.node },
            { key: 'c', label: 'Calls', num: true, cell: (r) => count(r.calls) },
            { key: 'd', label: 'Duration', num: true, bar: (r) => (r.duration_s == null || max === 0 ? null : (r.duration_s / max) * 100), cell: (r) => duration(r.duration_s) },
            { key: 's', label: 'State', cell: (r) => statusBadge(r.state) },
          ]}
        />
        );
      }}
    </Block>
  );
}

function NodeDocDrawer({ node, onClose }: { node: string | null; onClose: () => void }) {
  const [env, setEnv] = useState<Envelope<NodeDocument> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!node) return;
    let cancel = false;
    setEnv(null);
    setErr(null);
    dqGet<NodeDocument>(`/pipeline/runs/latest/nodes/selected/document?node=${encodeURIComponent(node)}`).then(
      (e) => { if (!cancel) setEnv(e); },
      (e: unknown) => { if (!cancel) setErr(e instanceof Error ? e.message : 'failed'); },
    );
    return () => { cancel = true; };
  }, [node]);
  const d = env?.data;
  const ps = paras(d?.paragraphs);
  return (
    <Drawer open={node !== null} onClose={onClose} no="22" label={node ? `Document · ${node}` : 'Document'}>
      {err ? <StateBlock kind="error" title="Withheld." why={err} />
        : !d ? <p className="note mute">loading…</p>
        : (
          <Prose lead={d.title ?? undefined}>
            {ps.map((p, i) => <p key={i}>{p}</p>)}
            {d.note ? <p className="pl-note">{d.note}</p> : null}
            {!d.title && !ps.length && !d.note ? <p>no document for this node</p> : null}
          </Prose>
        )}
    </Drawer>
  );
}

/** GET /pipeline/runs/latest/artifacts — documents each node wrote. A row opens that node's document. */
export function PlArtifactLedgerBlock() {
  const [node, setNode] = useState<string | null>(null);
  return (
    <>
    <Block<ArtifactLedger> no="25" label="Artifact ledger" route="/pipeline/runs/latest/artifacts">
      {(d) => (
        <DataTable
          rows={d.rows}
          rowKey={(r, i) => `${r.node}:${i}`}
          empty="no artifacts"
          onRowClick={(r) => { if (r.node) setNode(r.node); }}
          cols={[
            { key: 's', label: 'Stage', cell: (r) => text(r.stage) },
            { key: 'n', label: 'Node', wrap: true, cell: (r) => r.node },
            { key: 'd', label: 'Document', wrap: true, cell: (r) => (r.document ? r.document : <>{dash} {r.state_only ? <Badge>state only</Badge> : null}</>) },
            { key: 'a', label: 'Date', cell: (r) => text(r.date) },
          ]}
        />
      )}
    </Block>
    <NodeDocDrawer node={node} onClose={() => setNode(null)} />
    </>
  );
}

/* ---------------- Strategies ---------------- */

/** GET /strategies/summary — catalog counters and the product-vision notice. */
export function StKpisBlock() {
  return (
    <Block<StrategiesSummary> no="26" label="Strategies · summary" route="/strategies/summary">
      {(d) => (
        <>
          {soon(d.notice)}
          <KpiGrid items={[
            { label: 'Catalog', value: count(d.catalog) },
            { label: 'Deployable', value: count(d.deployable) },
            { label: 'My deployments', value: count(d.deployments) },
            { label: 'Paper accounts', value: count(d.paper_accounts) },
            { label: 'Portfolios', value: count(d.portfolios) },
            { label: 'Brokers', value: count(d.brokers) },
            { label: 'Plan', value: text(d.plan) },
            { label: 'Last run', value: text(d.last_run) },
          ]} />
        </>
      )}
    </Block>
  );
}

/** GET /strategies — strategy catalog. */
export function StCatalogBlock() {
  return (
    <Block<StrategyCatalog> no="27" label="Catalog" route="/strategies">
      {(d) => (
        <DataTable
          rows={d.strategies}
          rowKey={(s, i) => `${s.id}:${i}`}
          empty="no strategies"
          cols={[
            { key: 'i', label: 'ID', cell: (s) => s.id },
            { key: 'n', label: 'Strategy', wrap: true, cell: (s) => s.name },
            { key: 'f', label: 'Family', wrap: true, cell: (s) => text(s.family) },
            { key: 'u', label: 'Universe', wrap: true, cell: (s) => text(s.universe) },
            { key: 'c', label: 'Cadence', cell: (s) => text(s.cadence) },
            { key: 't', label: 'Targets', wrap: true, cell: (s) => (Array.isArray(s.targets) && s.targets.length ? s.targets.join(', ') : dash) },
            { key: 's', label: 'Status', cell: (s) => statusBadge(s.status) },
            { key: 'd', label: 'Deploy', cell: (s) => statusBadge(s.deploy) },
          ]}
        />
      )}
    </Block>
  );
}

/** GET /strategies/deployments — my deployments. */
export function StDeploymentsBlock() {
  return (
    <Block<StrategyDeployments> no="28" label="My deployments" route="/strategies/deployments">
      {(d) => (Array.isArray(d.deployments) && d.deployments.length ? (
        <DataTable
          rows={d.deployments}
          rowKey={(r, i) => `${r.id}:${i}`}
          cols={[
            { key: 'i', label: 'Deployment', cell: (r) => r.id },
            { key: 's', label: 'Strategy', cell: (r) => text(r.strategy_id) },
            { key: 't', label: 'Target', wrap: true, cell: (r) => text(r.target) },
            { key: 'st', label: 'Status', cell: (r) => statusBadge(r.status) },
            { key: 'l', label: 'Last run', cell: (r) => text(r.last_run) },
          ]}
        />
      ) : <StateBlock kind="empty" title="No deployments yet." why={d.empty_reason ?? undefined} />)}
    </Block>
  );
}

/** GET /strategies/targets — what a strategy can be bound to. */
export function StTargetsBlock() {
  return (
    <Block<StrategyTargets> no="29" label="Deployment targets" route="/strategies/targets">
      {(d) => (
        <DataTable
          rows={d.targets}
          rowKey={(t, i) => `${t.target}:${i}`}
          empty="no targets"
          cols={[
            { key: 't', label: 'Target', cell: (t) => t.target },
            { key: 'd', label: 'What it is', wrap: true, cell: (t) => text(t.description) },
            { key: 's', label: 'Status', cell: (t) => statusBadge(t.status) },
          ]}
        />
      )}
    </Block>
  );
}

/** GET /strategies/default — strategy overview. TODO: id selection from the catalog row. */
export function StOverviewBlock() {
  return (
    <Block<StrategyOverview> no="30" label="Overview" route="/strategies/default" asOf={(d) => d.id}>
      {(d) => (
        <>
          {d.name || d.lede ? <Prose lead={d.name ?? undefined}>{d.lede ? <p>{d.lede}</p> : null}</Prose> : null}
          <KvList rows={[
            { k: 'Family', v: text(d.family) },
            { k: 'Universe', v: text(d.universe) },
            { k: 'Cadence', v: text(d.cadence) },
            { k: 'Targets', v: text(d.targets) },
            { k: 'Related thesis', v: text(d.related_thesis) },
            { k: 'Execution', v: text(d.execution) },
          ]} />
        </>
      )}
    </Block>
  );
}

/** GET /strategies/default/parameters — read-only parameters; state shown beside the value. */
export function StParametersBlock() {
  return (
    <Block<StrategyParameters> no="31" label="Parameters" route="/strategies/default/parameters">
      {(d) => (Array.isArray(d.parameters) && d.parameters.length ? (
        <KvList rows={d.parameters.map((p, i) => ({ k: p.name || `param ${i + 1}`, mono: true, v: `${p.value == null ? dash : String(p.value)}${p.state ? ` · ${p.state}` : ''}` }))} />
      ) : withheld('parameters'))}
    </Block>
  );
}

/** GET /strategies/default/performance — paper track record; unavailable is stated, never estimated. */
export function StTrackRecordBlock() {
  return (
    <Block<StrategyPerformance> no="32" label="Paper track record" route="/strategies/default/performance">
      {(d) => {
        const pts = (Array.isArray(d.points) ? d.points : []).filter((p) => p && typeof p.date === 'string');
        if (!d.available || !pts.length) return <StateBlock kind="empty" title="Not available." why={d.reason ?? 'No deployment has run, and nothing is estimated in its place.'} />;
        return (
          <>
            <LineChart series={[{ name: 'value', values: pts.map((p) => p.value) }]} labels={pts.map((p) => p.date)} />
            <DataTable
              rows={[...pts].reverse().slice(0, 30)}
              rowKey={(p, i) => `${p.date}:${i}`}
              cols={[
                { key: 'd', label: 'Date', cell: (p) => p.date },
                { key: 'v', label: 'Value', num: true, cell: (p) => (p.value == null || !Number.isFinite(p.value) ? dash : p.value.toFixed(3)) },
              ]}
            />
          </>
        );
      }}
    </Block>
  );
}

/** GET /strategies/default/runs — runs of the strategy's deployments. */
export function StRunsBlock() {
  return (
    <Block<StrategyRuns> no="33" label="Runs" route="/strategies/default/runs">
      {(d) => (Array.isArray(d.runs) && d.runs.length ? (
        <DataTable
          rows={d.runs}
          rowKey={(r, i) => `${r.run_date}:${i}`}
          cols={[
            { key: 'd', label: 'Run', cell: (r) => r.run_date },
            { key: 'p', label: 'Deployment', cell: (r) => text(r.deployment_id) },
            { key: 's', label: 'Status', cell: (r) => statusBadge(r.status) },
          ]}
        />
      ) : <StateBlock kind="empty" title="No runs." why={d.empty_reason ?? undefined} />)}
    </Block>
  );
}

/** GET /strategies/deploy-flow — the planned deploy steps. Display only; no write is wired. */
export function StDeployFlowBlock() {
  return (
    <Block<DeployFlow> no="34" label="Deploy · plan" route="/strategies/deploy-flow">
      {(d) => (Array.isArray(d.steps) && d.steps.length ? (
        <Stepper steps={d.steps.map((s) => ({
          label: s.label,
          state: s.state === 'done' || s.state === 'active' || s.state === 'failed' ? s.state : 'todo',
          detail: <>{s.detail ?? ''} {s.status ? statusBadge(s.status) : null}</>,
        }))} />
      ) : withheld('deploy steps'))}
    </Block>
  );
}

/** GET /strategies/default/deploy-draft — draft target (read-only; deploy is not built). */
export function StDeployDraftBlock() {
  return (
    <Block<DeployDraft> no="35" label="Target · paper" route="/strategies/default/deploy-draft">
      {(d) => (
        <>
          {soon(d.notice)}
          <KvList rows={[
            { k: 'Target kind', v: text(d.target_kind) },
            { k: 'Paper capital', v: text(d.paper_capital), mono: true },
            { k: 'Broker', v: text(d.broker) },
            { k: 'Portfolio', v: text(d.portfolio) },
            { k: 'Schedule', v: text(d.schedule) },
          ]} />
        </>
      )}
    </Block>
  );
}

export type PipelineBlockDef = { id: string; title: string; route: string; Component: ComponentType };
export const PIPELINE_BLOCKS: PipelineBlockDef[] = [
  { id: 'pl-run-health', title: 'Run health', route: '/pipeline/runs/latest/health', Component: PlRunHealthBlock },
  { id: 'pl-canvas', title: 'Canvas · inputs to learning', route: '/pipeline/runs/latest/graph', Component: PlCanvasBlock },
  { id: 'pl-node-document', title: 'Node document', route: '/pipeline/runs/latest/nodes/selected/document', Component: PlNodeDocumentBlock },
  { id: 'pl-narrative', title: 'Run narrative', route: '/pipeline/runs/latest/narrative', Component: PlNarrativeBlock },
  { id: 'pl-call-trace', title: 'Call trace', route: '/pipeline/runs/latest/trace', Component: PlCallTraceBlock },
  { id: 'pl-artifacts', title: 'Artifact ledger', route: '/pipeline/runs/latest/artifacts', Component: PlArtifactLedgerBlock },
  { id: 'st-kpis', title: 'Strategies · summary', route: '/strategies/summary', Component: StKpisBlock },
  { id: 'st-catalog', title: 'Catalog', route: '/strategies', Component: StCatalogBlock },
  { id: 'st-deployments', title: 'My deployments', route: '/strategies/deployments', Component: StDeploymentsBlock },
  { id: 'st-targets', title: 'Deployment targets', route: '/strategies/targets', Component: StTargetsBlock },
  { id: 'st-overview', title: 'Overview', route: '/strategies/default', Component: StOverviewBlock },
  { id: 'st-parameters', title: 'Parameters', route: '/strategies/default/parameters', Component: StParametersBlock },
  { id: 'st-track-record', title: 'Paper track record', route: '/strategies/default/performance', Component: StTrackRecordBlock },
  { id: 'st-runs', title: 'Runs', route: '/strategies/default/runs', Component: StRunsBlock },
  { id: 'st-deploy-flow', title: 'Deploy · plan', route: '/strategies/deploy-flow', Component: StDeployFlowBlock },
  { id: 'st-deploy-draft', title: 'Target · paper', route: '/strategies/default/deploy-draft', Component: StDeployDraftBlock },
];
