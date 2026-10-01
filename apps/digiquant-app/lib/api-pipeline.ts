/**
 * Route payloads for the Pipeline + Strategies blocks (BLOCKS.md "Pipeline / strategies").
 * Each type is the envelope `data` shape. Nothing here exists in the worker yet; every
 * field the worker may not return is optional/nullable and renders "—" or a withheld state.
 * `latest` stands in for `:date` and `default` for strategy `:id` until selection lands.
 */

/** Node/stage/run states are open strings so a new worker state never breaks rendering. */
export type PlState = 'ok' | 'carried' | 'failed' | 'running' | 'idle' | 'skipped' | 'not_persisted' | (string & {});

/** GET /pipeline/runs/latest/health */
export type PipelineHealth = {
  run_date: string | null;
  run_type: string | null;
  status: string | null;
  config: string | null;
  posture: string | null;
  nodes?: { ok: number | null; carried: number | null; failed: number | null } | null;
  /** persisted=false is a typed gap, not a failure. */
  inputs_calls?: { persisted: boolean | null; note?: string | null } | null;
  calls?: number | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
  cost_usd?: number | null;
};

/** GET /pipeline/runs/latest/graph */
export type PipelineGraph = {
  run_date: string | null;
  selected_node: string | null;
  nodes: { id: string; label: string; stage: string | null; col: number; state?: PlState | null; to?: string[] | null }[];
};

/** GET /pipeline/runs/latest/nodes/selected/document — the selected (default) node's document. */
export type NodeDocument = {
  run_date: string | null;
  node_id: string | null;
  title: string | null;
  paragraphs?: string[] | null;
  /** Soft footnote under the document. */
  note?: string | null;
};

/** GET /pipeline/runs/latest/narrative — the /why narrative. */
export type RunNarrative = {
  run_date: string | null;
  heading: string | null;
  paragraphs?: string[] | null;
};

/** GET /pipeline/runs/latest/trace */
export type CallTrace = {
  rows: { node: string; calls: number | null; duration_s: number | null; state: PlState | null }[];
};

/** GET /pipeline/runs/latest/artifacts */
export type ArtifactLedger = {
  rows: { stage: string | null; node: string; document: string | null; date: string | null; state_only?: boolean | null }[];
};

/** GET /strategies/summary */
export type StrategiesSummary = {
  catalog: number | null;
  deployable: number | null;
  deployments: number | null;
  paper_accounts: number | null;
  portfolios: number | null;
  brokers: number | null;
  plan: string | null;
  last_run: string | null;
  /** Product-vision notice shown in a soon-bar; null = no notice. */
  notice?: { tag: 'soon' | 'wip'; text: string } | null;
};

/** GET /strategies */
export type StrategyCatalog = {
  strategies: { id: string; name: string; family: string | null; universe: string | null; cadence: string | null; targets: string[] | null; status: string | null; deploy: string | null }[];
};

/** GET /strategies/deployments */
export type StrategyDeployments = {
  deployments: { id: string; strategy_id: string | null; target: string | null; status: string | null; last_run: string | null }[];
  /** Why the list is empty, when the worker knows. */
  empty_reason?: string | null;
};

/** GET /strategies/targets */
export type StrategyTargets = { targets: { target: string; description: string | null; status: string | null }[] };

/** GET /strategies/default */
export type StrategyOverview = {
  id: string | null;
  name: string | null;
  lede: string | null;
  family: string | null;
  universe: string | null;
  cadence: string | null;
  targets: string | null;
  related_thesis: string | null;
  execution: string | null;
};

/** GET /strategies/default/parameters */
export type StrategyParameters = { parameters: { name: string; value: string | number | null; state: string | null }[] };

/** GET /strategies/default/performance — available=false means no deployment ran; nothing is estimated. */
export type StrategyPerformance = {
  available: boolean;
  reason?: string | null;
  points?: { date: string; value: number | null }[] | null;
};

/** GET /strategies/default/runs */
export type StrategyRuns = {
  runs: { run_date: string; status: string | null; deployment_id: string | null }[];
  empty_reason?: string | null;
};

/** GET /strategies/deploy-flow */
export type DeployFlow = {
  steps: { label: string; detail: string | null; state: 'done' | 'active' | 'todo' | 'failed'; status: string | null }[];
};

/** GET /strategies/default/deploy-draft (read-only; deploy itself is not built). */
export type DeployDraft = {
  target_kind: string | null;
  paper_capital: string | null;
  broker: string | null;
  portfolio: string | null;
  schedule: string | null;
  notice?: { tag: 'soon' | 'wip'; text: string } | null;
};
