'use client';

import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import { Badge } from '@/components/ui';
import {
  Layers, Clock, Zap, Bot, Database, Globe,
} from 'lucide-react';

interface Phase {
  n: string;
  name: string;
  output: string;
  desc: string;
}

interface AgentEntry {
  name: string;
  file: string;
  role: string;
}

// Atlas — the research graph (A0–A8). Market data in, a canonical digest out.
const ATLAS_PHASES: Phase[] = [
  { n: 'A0', name: 'Preflight',                output: 'prior context + market data',  desc: 'Loads prior runs and Supabase snapshots, plus FRED macro and price history' },
  { n: 'A1', name: 'Triage',                   output: 'carry / regenerate',           desc: 'Price + fingerprint deltas mark quiet segments to carry (zero LLM) vs. regenerate' },
  { n: 'A2', name: 'Alternative data ×6',      output: '6× segment JSON',              desc: 'Sentiment, CTA positioning, options/derivatives, politician signals, on-chain, AI portfolios' },
  { n: 'A3', name: 'Institutional ×2',         output: '2× segment JSON',              desc: 'ETF & fund flows; hedge-fund and smart-money intelligence' },
  { n: 'A4', name: 'Macro',                    output: 'regime JSON',                  desc: 'FRED-driven growth / inflation / policy / risk-appetite; web search only if FRED is stale' },
  { n: 'A5', name: 'Asset class ×5',           output: '5× segment JSON',              desc: 'Bonds, commodities, forex, crypto, international' },
  { n: 'A6', name: 'Equity + 11 GICS sectors', output: 'scorecard JSON',               desc: 'Top-down SPY/QQQ/IWM, then per-sector relative strength → overweight / underweight scorecard' },
  { n: 'A7', name: 'Consolidate',              output: 'bias row → daily_snapshots',   desc: 'Cross-segment consolidation ahead of synthesis' },
  { n: 'A8', name: 'Digest synthesis',         output: 'DigestSnapshot',               desc: 'Canonical digest — the handoff contract to Hermes (no data tools, no web search)' },
];

// Hermes — the portfolio graph (H1–H9). Runs only if Atlas produced research.
const HERMES_PHASES: Phase[] = [
  { n: 'H1', name: 'Thesis review',             output: 'ThesisReviewPayload',          desc: 'Re-scores the active theses carried from prior runs' },
  { n: 'H2', name: 'Market thesis exploration', output: 'MarketThesis[]',               desc: 'Infers new market theses from the digest' },
  { n: 'H3', name: 'Vehicle map',               output: 'VehicleMap',                   desc: 'Maps each thesis to tradeable vehicle tickers' },
  { n: 'H4', name: 'Opportunity screener',      output: 'focus roster',                 desc: 'Holdings + thesis-mapped + top-scored candidates, capped to a focus roster' },
  { n: 'H5', name: 'Asset analysts ×N',         output: 'AnalystPayload / ticker',      desc: 'Per-ticker conviction (−5..+5), stance and thesis link — fans out across the roster' },
  { n: 'H6', name: 'Deliberation ×N',           output: 'DeliberationSummary / ticker', desc: 'The PM challenges each analyst; the analyst responds; 2–10 rounds until convergence' },
  { n: 'H7', name: 'PM direction',              output: 'PMDirectionMemo',              desc: 'Direction and conviction rank across the book (no weights yet)' },
  { n: 'H8', name: 'Risk sizing',               output: 'RebalancePayload',             desc: 'A deterministic sizer turns the memo into sized target weights' },
  { n: 'H9', name: 'Commit run',                output: 'BookedPortfolio',              desc: 'Upserts positions, NAV, decision_log, theses and the brief — idempotent on fingerprint' },
];

// Real LangGraph phase nodes — verified against the code (2026-06-22).
const AGENTS: AgentEntry[] = [
  { name: 'Atlas · Alt data',      file: 'atlas/phases/phase1_altdata.py',       role: 'Six parallel alternative-data sub-nodes' },
  { name: 'Atlas · Institutional', file: 'atlas/phases/phase2_institutional.py', role: 'ETF flows + hedge-fund intel' },
  { name: 'Atlas · Macro',         file: 'atlas/phases/phase3_macro.py',         role: 'FRED regime; web fallback when stale' },
  { name: 'Atlas · Asset class',   file: 'atlas/phases/phase4_assetclass.py',    role: 'Bonds, commodities, FX, crypto, international' },
  { name: 'Atlas · Equities',      file: 'atlas/phases/phase5_equities.py',      role: 'Breadth, factors, 11 GICS sectors' },
  { name: 'Atlas · Consolidate',   file: 'atlas/phases/phase6_consolidate.py',   role: 'Cross-segment bias row' },
  { name: 'Atlas · Synthesis',     file: 'atlas/phases/phase7_synthesis.py',     role: 'Canonical digest snapshot' },
  { name: 'Hermes · Theses',       file: 'hermes/phases/h1_thesis_review.py',    role: 'Review → explore → vehicle-map (H1–H3)' },
  { name: 'Hermes · Screener',     file: 'hermes/phases/h4_opportunity_screener.py', role: 'Builds the focus roster (H4)' },
  { name: 'Hermes · Analysts',     file: 'hermes/phases/h5_asset_analyst.py',    role: 'Per-ticker conviction, fan-out (H5)' },
  { name: 'Hermes · Deliberation', file: 'hermes/phases/h6_deliberation.py',     role: 'PM ⇄ analyst challenge loop, fan-out (H6)' },
  { name: 'Hermes · PM direction', file: 'hermes/phases/h7_pm_direction.py',     role: 'Direction + conviction rank (H7)' },
  { name: 'Hermes · Risk sizing',  file: 'hermes/phases/phase7e_risk_sizing.py', role: 'Deterministic weight sizer (H8)' },
  { name: 'Hermes · Commit',       file: 'hermes/phases/h9_commit_run.py',       role: 'Books positions, NAV, decision_log (H9)' },
];

// Supabase tables written by a daily run.
const PERSISTENCE: { table: string; what: string }[] = [
  { table: 'documents',             what: 'Every published segment, digest, analyst note and brief' },
  { table: 'daily_snapshots',       what: 'The digest + cross-segment bias row, per run date' },
  { table: 'positions',             what: 'Booked target weights per ticker (+ CASH)' },
  { table: 'nav_history',           what: 'Daily NAV index (base 100), cash and invested %' },
  { table: 'theses',                what: 'Active market theses and their status' },
  { table: 'thesis_vehicles',       what: 'Thesis → vehicle-ticker mapping' },
  { table: 'decision_log',          what: 'Per-ticker outcomes: new / changed / held / exited' },
  { table: 'analyst_coverage',      what: 'Per-ticker analyst runs and thesis links' },
  { table: 'atlas_run_diagnostics', what: 'Run telemetry: segment counts, tokens, errors, timing' },
];

const STATS = [
  { label: 'Atlas phases', value: 'A0–A8' },
  { label: 'Hermes phases', value: 'H1–H9' },
  { label: 'GICS sectors', value: '11' },
  { label: 'Run cadence', value: 'Daily' },
];

function PhaseTable({ phases, accent }: { phases: Phase[]; accent: string }) {
  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-0 text-sm md:min-w-[640px]">
          <thead>
            <tr className="text-text-muted text-xs uppercase tracking-wider border-b border-border-subtle bg-bg-secondary">
              <th className="text-left px-5 py-3 w-16">Node</th>
              <th className="text-left px-5 py-3">Phase</th>
              <th className="text-left px-5 py-3">Output</th>
              <th className="text-left px-5 py-3">What it does</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {phases.map(p => (
              <tr key={p.n} className="hover:bg-white/[0.02]">
                <td className={`px-5 py-3 font-mono font-bold ${accent}`}>{p.n}</td>
                <td className="px-5 py-3 font-medium">{p.name}</td>
                <td className="px-5 py-3 font-mono text-[0.8rem] text-text-muted">{p.output}</td>
                <td className="px-5 py-3 text-text-secondary text-[0.85rem]">{p.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ArchitecturePage() {
  return (
    <div className={`${SUBPAGE_MAX} space-y-8 py-4 md:py-6`}>
      <header className="space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">
          System guide
        </p>
        <h1 className="font-display text-4xl font-normal tracking-tight text-text-primary sm:text-5xl">
          How Olympus works
        </h1>
        <p className="max-w-3xl text-sm leading-relaxed text-text-secondary">
          Once a trading day, <strong className="text-text-primary">Atlas</strong> researches the market and{' '}
          <strong className="text-text-primary">Hermes</strong> turns that research into a deliberated, booked
          portfolio. Both run as one LangGraph chain; Supabase holds the canonical state the dashboard reads.
        </p>
      </header>

      {/* Intro */}
      <div className="glass-card p-6">
        <p className="text-sm text-text-secondary leading-relaxed max-w-3xl">
          The whole run is one command —{' '}
          <code className="text-fin-blue">python -m digiquant.olympus.hermes.chain --cadence daily</code>.
          State is <strong className="text-text-primary">DB-first</strong>: phases publish JSON artifacts and
          snapshots to Supabase as the source of truth, and the markdown you read in the app is derived from them.
          Hermes runs only if Atlas produced research, so a thin research day never books a portfolio on noise.
        </p>
      </div>

      {/* Pipeline flow */}
      <div className="glass-card p-6">
        <h2 className="font-display text-xl font-normal mb-3">Pipeline flow</h2>
        <div className="flex flex-wrap items-stretch gap-2 text-xs sm:text-sm">
          {['Schedule', 'Atlas research', 'Digest', 'Hermes deliberation', 'Book & NAV', 'Publish'].map((label, i, arr) => (
            <div key={label} className="flex items-center gap-2">
              <div className="rounded-lg border border-border-subtle bg-bg-secondary/60 px-3 py-2 text-center">
                <span className="text-text-primary font-medium">{label}</span>
              </div>
              {i < arr.length - 1 ? (
                <span className="text-text-muted hidden sm:inline" aria-hidden>→</span>
              ) : null}
            </div>
          ))}
        </div>
        <p className="text-xs text-text-muted mt-3 max-w-3xl">
          The scheduled run ingests market inputs, Atlas writes a canonical digest, Hermes deliberates a portfolio
          from it, and the commit step books positions and NAV. Every step persists to Supabase for the dashboard.
        </p>
      </div>

      {/* Cadence & control */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Clock size={16} className="text-fin-blue" />
          <h2 className="font-display text-xl font-normal">Cadence &amp; control</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="glass-card p-5 border-t-2 border-fin-blue/40">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-bold">Daily run</h3>
              <Badge variant="default">Mon–Fri</Badge>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">
              One unified Atlas→Hermes graph per trading day, scheduled at 12:00 UTC. There is no separate weekly or
              monthly graph — that three-tier model was retired.
            </p>
          </div>
          <div className="glass-card p-5 border-t-2 border-fin-green/40">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-bold">Refresh scope</h3>
              <Badge variant="green">cost knob</Badge>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">
              <code className="text-fin-blue">--refresh-scope all</code> forces a full rewrite (a baseline);
              otherwise triage carries quiet segments forward to save tokens.
            </p>
          </div>
          <div className="glass-card p-5 border-t-2 border-fin-amber/40">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-bold">Operator controls</h3>
              <Badge variant="amber">manual</Badge>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">
              <code className="text-fin-blue">--dry-run</code> compiles the graphs without LLM calls;{' '}
              <code className="text-fin-blue">--watchlist</code> narrows focus;{' '}
              <code className="text-fin-blue">--resume-run-id</code> resumes from a checkpoint.
            </p>
          </div>
        </div>
      </div>

      {/* Atlas phases */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Zap size={16} className="text-fin-blue" />
          <h2 className="font-display text-xl font-normal">Atlas — research graph</h2>
        </div>
        <PhaseTable phases={ATLAS_PHASES} accent="text-fin-blue" />
      </div>

      {/* Hermes phases */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Layers size={16} className="text-fin-green" />
          <h2 className="font-display text-xl font-normal">Hermes — portfolio graph</h2>
        </div>
        <PhaseTable phases={HERMES_PHASES} accent="text-fin-green" />
        <p className="text-xs text-text-muted mt-3 max-w-3xl">
          H5 and H6 fan out across the focus roster — one analyst and one PM⇄analyst deliberation per ticker.
          NAV is a base-100 index seeded at 100 on the first run, then chained by daily position returns — not
          notional dollars.
        </p>
      </div>

      {/* Grounding + routing */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-2">
            <Globe size={16} className="text-fin-blue" />
            <h2 className="font-display text-lg font-normal">Web grounding</h2>
          </div>
          <p className="text-sm text-text-secondary leading-relaxed">
            Grounding is a separate pre-pass, not an in-model tool. For alt-data, institutional and macro phases it
            fetches cited web summaries and injects them into the prompt before the phase LLM runs — so phase models
            never need a web-search variant themselves.
          </p>
        </div>
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-2">
            <Bot size={16} className="text-fin-green" />
            <h2 className="font-display text-lg font-normal">Model routing</h2>
          </div>
          <p className="text-sm text-text-secondary leading-relaxed">
            Each phase hashes to a capability pool — <span className="font-mono text-text-primary">extraction</span>,{' '}
            <span className="font-mono text-text-primary">research</span> or{' '}
            <span className="font-mono text-text-primary">reasoning</span> — while grounding draws from a distinct
            web-search pool. Swap the whole roster by tier: <code className="text-fin-blue">cheap</code>,{' '}
            <code className="text-fin-blue">balanced</code> or <code className="text-fin-blue">quality</code>.
          </p>
        </div>
      </div>

      {/* Persistence */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Database size={16} className="text-fin-blue" />
          <h2 className="font-display text-xl font-normal">What a run persists</h2>
        </div>
        <div className="glass-card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-0 text-sm md:min-w-[520px]">
              <tbody className="divide-y divide-border-subtle">
                {PERSISTENCE.map(row => (
                  <tr key={row.table} className="hover:bg-white/[0.02]">
                    <td className="px-5 py-3 font-mono text-[0.82rem] text-fin-blue whitespace-nowrap">{row.table}</td>
                    <td className="px-5 py-3 text-text-secondary text-[0.85rem]">{row.what}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Agent file map */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Bot size={16} className="text-fin-green" />
          <h2 className="font-display text-xl font-normal">Phase map</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {AGENTS.map(a => (
            <div key={a.name} className="glass-card p-4">
              <h3 className="text-sm font-bold mb-1 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-fin-green shrink-0" />
                {a.name}
              </h3>
              <p className="text-xs text-text-secondary leading-relaxed">{a.role}</p>
              <code className="mt-2 inline-block rounded-md border border-border-subtle bg-bg-secondary px-1.5 py-1 font-mono text-[10px] text-text-muted">
                {a.file}
              </code>
            </div>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {STATS.map(s => (
          <div key={s.label} className="glass-card p-4 text-center">
            <p className="font-display text-3xl font-normal text-fin-blue">{s.value}</p>
            <p className="text-xs text-text-muted mt-1">{s.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
