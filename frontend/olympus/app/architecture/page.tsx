'use client';

import { ElementType } from 'react';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import { Badge } from '@/components/ui';
import {
  Layers, Clock, Zap, Bot, Database, Globe,
} from 'lucide-react';

interface CadenceTier {
  label: string;
  when: string;
  desc: string;
  cost: string;
  color: string;
}

interface AnalysisPhase {
  n: number | string;
  name: string;
  output: string;
  desc: string;
  icon?: ElementType<{ size?: number; className?: string }>;
}

interface AgentEntry {
  name: string;
  file: string;
  role: string;
}

const CADENCE_TIERS: CadenceTier[] = [
  { label: 'Sunday Baseline', when: 'Sunday',    desc: 'Full 9-phase pipeline — all 20+ files from scratch', cost: '100%',    color: 'fin-blue' },
  { label: 'Daily Delta',     when: 'Mon–Sat',   desc: 'Lightweight delta — only changed segments',          cost: '~20–30%', color: 'fin-green' },
  { label: 'Monthly Synthesis', when: 'Month-end', desc: 'Review of all baselines + deltas for the month',  cost: '~40–50%', color: 'fin-purple' },
];

const PHASES: AnalysisPhase[] = [
  { n: 1,     name: 'Alternative Data',     output: 'segment JSON → Supabase', desc: 'Sentiment, CTA, options, political signals (canonical JSON; MD derived)', icon: Database },
  { n: 2,     name: 'Institutional Intel',  output: 'segment JSON → Supabase', desc: 'ETF flows, hedge fund activity, smart money', icon: Layers },
  { n: 3,     name: 'Macro Analysis',       output: 'segment JSON → Supabase', desc: 'Rates, regime, VIX, DXY, leading indicators', icon: Globe },
  { n: '4A',  name: 'Bonds & Rates',        output: 'segment JSON → Supabase', desc: 'Treasury yields, credit spreads, duration' },
  { n: '4B',  name: 'Commodities',          output: 'segment JSON → Supabase', desc: 'Energy, metals, agriculture' },
  { n: '4C',  name: 'Forex',                output: 'segment JSON → Supabase', desc: 'DXY, majors, EM FX' },
  { n: '4D',  name: 'Crypto',               output: 'segment JSON → Supabase', desc: 'BTC, ETH, on-chain, alt rotation' },
  { n: '4E',  name: 'International',        output: 'segment JSON → Supabase', desc: 'EFA, EEM, country risk' },
  { n: '5A',  name: 'US Equities',          output: 'segment JSON → Supabase', desc: 'SPY, QQQ, breadth, factors' },
  { n: '5B–L', name: '11 GICS Sectors',     output: 'sectors/*.json',     desc: 'Per-sector JSON → Supabase documents' },
  { n: 7,     name: 'Digest Synthesis',     output: 'snapshot.json + daily_snapshots', desc: 'Canonical digest JSON; documents.digest; markdown derived for UI' },
];

const AGENTS: AgentEntry[] = [
  { name: 'Orchestrator',   file: 'orchestrator.agent.md',        role: 'Pipeline driver — routes baseline vs delta' },
  { name: 'Sector Analyst', file: 'sector-analyst.agent.md',      role: 'Runs one or more GICS sector deep-dives' },
  { name: 'Alt Data',       file: 'alt-data-analyst.agent.md',    role: 'Phase 1 alternative data gathering' },
  { name: 'Institutional',  file: 'institutional-analyst.agent.md', role: 'Phase 2 smart money intelligence' },
  { name: 'Portfolio Mgr',  file: 'portfolio-manager.agent.md',   role: 'Position sizing, rebalancing, risk' },
  { name: 'Research Asst',  file: 'research-assistant.agent.md',  role: 'Ad-hoc research queries' },
  { name: 'Thesis Tracker', file: 'thesis-tracker.agent.md',      role: 'Portfolio thesis lifecycle management' },
];

export default function ArchitecturePage() {
  return (
    <div className={`${SUBPAGE_MAX} space-y-8 py-4 md:py-6`}>

        {/* Intro */}
        <div className="glass-card p-6">
          <p className="text-sm text-text-secondary leading-relaxed max-w-3xl">
            <strong className="text-white">Atlas</strong> is a daily market intelligence system driven by a
            multi-phase AI pipeline. <strong className="text-white">Canonical state is DB-first</strong> (Supabase):
            JSON artifacts and snapshots are the source of truth; markdown in the app is derived. GitHub Actions
            refresh prices and metrics; agents publish research and portfolio decisions via{' '}
            <code className="text-fin-blue">run_db_first.py</code> and related scripts.
          </p>
        </div>

        {/* Pipeline flow + data path (high level) */}
        <div className="glass-card p-6 space-y-6">
          <div>
            <h2 className="text-base font-semibold mb-3">Pipeline flow</h2>
            <div className="flex flex-wrap items-stretch justify-center gap-2 text-xs sm:text-sm">
              {['Schedule', 'Ingest', 'Agents', 'Validate', 'Publish'].map((label, i, arr) => (
                <div key={label} className="flex items-center gap-2">
                  <div className="rounded-lg border border-border-subtle bg-bg-secondary/60 px-3 py-2 text-center min-w-[88px]">
                    <span className="text-text-primary font-medium">{label}</span>
                  </div>
                  {i < arr.length - 1 ? (
                    <span className="text-text-muted hidden sm:inline" aria-hidden>
                      →
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
            <p className="text-xs text-text-muted mt-3 max-w-3xl">
              Scheduled runs trigger ingestion of market inputs; agent phases produce segment JSON and portfolio
              artifacts; validation gates writes; publish commits rows to Supabase for the Atlas UI.
            </p>
          </div>
          <div className="border-t border-border-subtle pt-5">
            <h2 className="text-base font-semibold mb-3">Data flow</h2>
            <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 sm:gap-3 text-xs sm:text-sm text-text-secondary">
              <span className="rounded-md border border-fin-blue/30 bg-fin-blue/10 px-3 py-1.5 font-mono text-fin-blue">
                Sources &amp; files
              </span>
              <span className="text-text-muted hidden sm:inline">→</span>
              <span className="rounded-md border border-fin-amber/30 bg-fin-amber/10 px-3 py-1.5 font-mono text-fin-amber">
                Python runners / agents
              </span>
              <span className="text-text-muted hidden sm:inline">→</span>
              <span className="rounded-md border border-fin-green/30 bg-fin-green/10 px-3 py-1.5 font-mono text-fin-green">
                Supabase (Postgres)
              </span>
              <span className="text-text-muted hidden sm:inline">→</span>
              <span className="rounded-md border border-border-subtle bg-bg-secondary px-3 py-1.5 font-mono text-text-primary">
                Next.js (Atlas)
              </span>
            </div>
            <p className="text-xs text-text-muted mt-3 max-w-3xl">
              The dashboard reads published documents, snapshots, and price history through typed queries; no
              filesystem reads occur in the browser.
            </p>
          </div>
        </div>

        {/* Three-Tier Cadence */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Clock size={16} className="text-fin-blue" />
            <h2 className="text-base font-semibold">Three-Tier Cadence</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {CADENCE_TIERS.map(t => (
              <div key={t.label} className={`glass-card p-5 border-t-2 border-${t.color}/40`}>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-bold">{t.label}</h3>
                  <Badge variant="default">{t.when}</Badge>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed mb-3">{t.desc}</p>
                <p className="text-xs text-text-muted">Token cost: <span className="text-white font-mono">{t.cost}</span></p>
              </div>
            ))}
          </div>
        </div>

        {/* 9-Phase Pipeline */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Zap size={16} className="text-fin-amber" />
            <h2 className="text-base font-semibold">9-Phase Pipeline</h2>
          </div>
          <div className="glass-card p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-0 text-sm md:min-w-[600px]">
                <thead>
                  <tr className="text-text-muted text-xs uppercase tracking-wider border-b border-border-subtle bg-bg-secondary">
                    <th className="text-left px-5 py-3 w-16">Phase</th>
                    <th className="text-left px-5 py-3">Analysis</th>
                    <th className="text-left px-5 py-3">Output</th>
                    <th className="text-left px-5 py-3">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {PHASES.map((p, i) => (
                    <tr key={i} className="hover:bg-white/[0.02]">
                      <td className="px-5 py-3 font-mono text-fin-blue font-bold">{p.n}</td>
                      <td className="px-5 py-3 font-medium">{p.name}</td>
                      <td className="px-5 py-3 font-mono text-[0.8rem] text-text-muted">{p.output}</td>
                      <td className="px-5 py-3 text-text-secondary text-[0.85rem]">{p.desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Agent Swarm */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Bot size={16} className="text-fin-green" />
            <h2 className="text-base font-semibold">Agent Swarm</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {AGENTS.map(a => (
              <div key={a.name} className="glass-card p-4">
                <h3 className="text-sm font-bold mb-1 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-fin-green shrink-0" />
                  {a.name}
                </h3>
                <p className="text-xs text-text-secondary leading-relaxed">{a.role}</p>
                <p className="text-[10px] text-text-muted font-mono mt-2">{a.file}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Pipeline Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Skill packages', value: '45+' },
            { label: 'Named Agents', value: '7' },
            { label: 'GICS Sectors', value: '11' },
            { label: 'Cadence', value: 'Sun baseline' },
          ].map(s => (
            <div key={s.label} className="glass-card p-4 text-center">
              <p className="text-2xl font-bold text-fin-blue">{s.value}</p>
              <p className="text-xs text-text-muted mt-1">{s.label}</p>
            </div>
          ))}
        </div>
    </div>
  );
}
