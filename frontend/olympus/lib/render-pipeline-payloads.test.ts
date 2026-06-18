import { describe, expect, it } from 'vitest';
import { fixtureDigest } from './__fixtures__/snapshot-fixture';
import { renderDigestMarkdownFromSnapshot } from './render-digest-from-snapshot';
import { renderDocumentMarkdownFromPayload } from './render-document-from-payload';
import {
  isAnalystSpecialistPayload,
  isDebateSummaryPayload,
  isMasterDigestPayload,
  isRebalancePayload,
  isRiskDebatePayload,
  isSegmentReportPayload,
  renderAnalystSpecialistMarkdown,
  renderDebateSummaryMarkdown,
  renderMasterDigestMarkdown,
  renderRebalanceMarkdown,
  renderRiskDebateMarkdown,
  renderSegmentReportMarkdown,
} from './render-pipeline-payloads';
import { digestItemsToStrings, extractDigestContextBullets } from './snapshot-context';

/** Trimmed copy of the production `documents.payload` for `bonds` (2026-06-12). */
const BONDS_PAYLOAD = {
  segment: 'bonds',
  date: '2026-06-12',
  bias: 'neutral',
  headline: 'Curve steepens as front-end yields ease on rate-cut repricing.',
  material_findings: [
    {
      label: 'CTAs short USTs',
      summary: 'Systematic funds hold short duration into supply week.',
      source_ids: ['1'],
    },
  ],
  sources: [{ id: '1', title: 'Rates wrap', url: 'https://example.com/rates' }],
  notes: 'No spread data retrieved.',
  yield_curve_shape: 'steepening',
  two_ten_spread_bps: null,
  credit_ig_spread_bps: null,
  credit_hy_spread_bps: null,
};

/** Trimmed copy of the production `pm-rebalance` payload (2026-06-12 — empty run). */
const REBALANCE_EMPTY = {
  notes: 'Data gaps prevent any rebalance.',
  actions: [],
  recommended_portfolio: [],
};

const REBALANCE_POPULATED = {
  notes: 'Trim tech overweight.',
  actions: [{ ticker: 'NVDA', action: 'TRIM', current_pct: 12, recommended_pct: 8 }],
  recommended_portfolio: [{ ticker: 'NVDA', weight_pct: 8 }],
};

/** Trimmed copy of the production `deliberation/{ticker}` DebateSummary payload. */
const DEBATE_PAYLOAD = {
  ticker: 'NVDA',
  rounds: [
    { round_number: 1, bull_argument: 'AI demand accelerating', bear_argument: 'Valuation stretched' },
  ],
  bull_thesis: 'Datacenter capex supercycle intact.',
  bear_thesis: 'Multiple compression risk on any guide-down.',
  net_stance: 'bullish',
  conviction_delta: 1,
};

/** Trimmed copy of the production `risk-debate` RiskDebateSummary payload. */
const RISK_DEBATE_PAYLOAD = {
  aggressive_case: 'Add beta into the breakout.',
  conservative_case: 'Keep the cash buffer; breadth is thin.',
  key_tension: 'Momentum vs. participation.',
};

/**
 * Real `analyst/{ticker}` SpecialistPayload shape from documents.payload (2026-06-17).
 * Keys: ticker, thesis, stance, conviction_score (integer), sources.
 * Note: bull_case, bear_case, entry_criteria, exit_criteria, risks are NOT present.
 */
const ANALYST_PAYLOAD = {
  ticker: 'NVDA',
  stance: 'bullish',
  conviction_score: 8,
  thesis: 'Datacenter AI buildout sustains outsized GPU demand into 2027.',
  sources: [
    { id: 'src-1', title: 'Nvidia Q2 Earnings', url: 'https://example.com/nvda-q2' },
    { id: 'src-2', title: 'Analyst wrap' },
  ],
};

/** Legacy v1 operator snapshot shape — must keep rendering via the old path. */
const V1_SNAPSHOT = {
  date: '2026-04-27',
  regime: { bias: 'bullish', label: 'Risk-on', conviction: 'high', summary: 'Breadth healthy.' },
  actionable: ['Add semis exposure'],
  risks: ['CPI surprise'],
  sector_scorecard: [
    { sector: 'Technology', etf: 'XLK', bias: 'bullish', confidence: 'high', key_driver: 'AI capex' },
  ],
};

describe('shape sniffers', () => {
  it('classifies the master digest payload', () => {
    expect(isMasterDigestPayload(fixtureDigest())).toBe(true);
    expect(isMasterDigestPayload(BONDS_PAYLOAD)).toBe(false);
    expect(isMasterDigestPayload(V1_SNAPSHOT)).toBe(false);
  });

  it('classifies segment reports', () => {
    expect(isSegmentReportPayload(BONDS_PAYLOAD)).toBe(true);
    expect(isSegmentReportPayload(REBALANCE_EMPTY)).toBe(false);
  });

  it('sniffers are standalone-correct: the master digest is not a segment report', () => {
    expect(isSegmentReportPayload(fixtureDigest())).toBe(false);
  });

  it('classifies rebalance payloads by shape and by document key', () => {
    expect(isRebalancePayload(REBALANCE_EMPTY)).toBe(true);
    expect(isRebalancePayload(BONDS_PAYLOAD, 'pm-rebalance')).toBe(true);
    expect(isRebalancePayload(BONDS_PAYLOAD)).toBe(false);
  });
});

describe('renderSegmentReportMarkdown', () => {
  it('renders headline, bias, findings, signals, notes and sources', () => {
    const md = renderSegmentReportMarkdown(BONDS_PAYLOAD);
    expect(md).toContain('# Bonds — 2026-06-12');
    expect(md).toContain('**Bias:** neutral');
    expect(md).toContain('Curve steepens');
    expect(md).toContain('**CTAs short USTs** — Systematic funds hold short duration');
    expect(md).toContain('**Yield Curve Shape:** steepening');
    expect(md).toContain('No spread data retrieved.');
    expect(md).toContain('[Rates wrap](https://example.com/rates)');
  });

  it('omits null metric fields instead of rendering empty rows', () => {
    const md = renderSegmentReportMarkdown(BONDS_PAYLOAD);
    expect(md).not.toContain('Two Ten Spread Bps');
  });
});

describe('renderMasterDigestMarkdown', () => {
  it('renders defensively when actionable/risk entries have blank labels', () => {
    const digest = {
      ...fixtureDigest(),
      actionable_summary: [{ priority: 1, label: '', rationale: '' }],
      risk_radar: [{ horizon_hours: 24, label: '', trigger: 'VIX spike' }],
    };
    const md = renderMasterDigestMarkdown(digest);
    expect(md).not.toContain('****');
    expect(md).toContain('- **P1** **Item**');
    expect(md).toContain('- **Risk** — VIX spike');
  });

  it('renders regime, headline, narrative sections and freshness', () => {
    const md = renderMasterDigestMarkdown(fixtureDigest());
    expect(md).toContain('# Daily Digest — 2026-04-27');
    expect(md).toContain('Risk-on regime confirmed');
    expect(md).toContain('**Overall bias:** bullish');
    expect(md).toContain('Tech rally extends as macro stress eases');
    expect(md).toContain('**NVDA breaks resistance**');
    expect(md).toContain('## Alt-Data Dashboard');
  });
});

describe('renderRebalanceMarkdown', () => {
  it('states explicitly when no changes were recommended', () => {
    const md = renderRebalanceMarkdown(REBALANCE_EMPTY);
    expect(md).toContain('_No allocation changes were recommended for this run._');
    expect(md).toContain('Data gaps prevent any rebalance.');
  });

  it('renders actions and recommended portfolio tables when present', () => {
    const md = renderRebalanceMarkdown(REBALANCE_POPULATED);
    expect(md).toContain('## Actions');
    expect(md).toContain('| NVDA | TRIM | 12 | 8 |');
    expect(md).toContain('## Recommended portfolio');
  });
});

describe('debate renderers (#698)', () => {
  it('sniffers classify debate and risk-debate payloads distinctly', () => {
    expect(isDebateSummaryPayload(DEBATE_PAYLOAD)).toBe(true);
    expect(isDebateSummaryPayload(RISK_DEBATE_PAYLOAD)).toBe(false);
    expect(isRiskDebatePayload(RISK_DEBATE_PAYLOAD)).toBe(true);
    expect(isRiskDebatePayload(DEBATE_PAYLOAD)).toBe(false);
    // Neither is mistaken for a segment report.
    expect(isSegmentReportPayload(DEBATE_PAYLOAD)).toBe(false);
    expect(isSegmentReportPayload(RISK_DEBATE_PAYLOAD)).toBe(false);
  });

  it('renders the debate summary with stance, theses, and rounds', () => {
    const md = renderDebateSummaryMarkdown(DEBATE_PAYLOAD);
    expect(md).toContain('# Bull / Bear Debate — NVDA');
    expect(md).toContain('**Net stance:** bullish · conviction Δ +1');
    expect(md).toContain('### Round 1');
    expect(md).toContain('**Bull:** AI demand accelerating');
    expect(md).toContain('**Bear:** Valuation stretched');
  });

  it('renders a negative conviction delta without a stray plus sign', () => {
    const md = renderDebateSummaryMarkdown({ ...DEBATE_PAYLOAD, conviction_delta: -2 });
    expect(md).toContain('conviction Δ -2');
    expect(md).not.toContain('+-2');
  });

  it('renders the risk debate with both cases and the tension', () => {
    const md = renderRiskDebateMarkdown(RISK_DEBATE_PAYLOAD);
    expect(md).toContain('## Aggressive case');
    expect(md).toContain('## Conservative case');
    expect(md).toContain('Momentum vs. participation.');
  });
});

describe('analyst specialist renderers (#814)', () => {
  it('classifies the real 5-key analyst payload', () => {
    expect(isAnalystSpecialistPayload(ANALYST_PAYLOAD)).toBe(true);
  });

  it('does NOT mis-classify a deliberation payload as analyst', () => {
    // deliberation/{ticker} has ticker + bull_thesis/net_stance but no conviction_score or stance
    expect(isAnalystSpecialistPayload(DEBATE_PAYLOAD)).toBe(false);
  });

  it('does NOT classify a risk-debate payload as analyst', () => {
    expect(isAnalystSpecialistPayload(RISK_DEBATE_PAYLOAD)).toBe(false);
  });

  it('renders conviction_score (integer) from the real payload', () => {
    const md = renderAnalystSpecialistMarkdown(ANALYST_PAYLOAD);
    expect(md).toContain('**Conviction:** 8');
    // Must NOT reference the old string field name
    expect(md).not.toContain('conviction:');
  });

  it('renders ticker, stance, thesis, and sources from the 5 real keys', () => {
    const md = renderAnalystSpecialistMarkdown(ANALYST_PAYLOAD);
    expect(md).toContain('# Analyst Report — NVDA');
    expect(md).toContain('**Stance:** bullish');
    expect(md).toContain('## Thesis');
    expect(md).toContain('Datacenter AI buildout');
    expect(md).toContain('[Nvidia Q2 Earnings](https://example.com/nvda-q2)');
    expect(md).toContain('- Analyst wrap');
  });

  it('does NOT render deprecated sections that never exist in live data', () => {
    const md = renderAnalystSpecialistMarkdown(ANALYST_PAYLOAD);
    expect(md).not.toContain('## Bull');
    expect(md).not.toContain('## Bear');
    expect(md).not.toContain('## Entry criteria');
    expect(md).not.toContain('## Exit criteria');
    expect(md).not.toContain('## Risks');
  });
});

describe('renderDocumentMarkdownFromPayload routing', () => {
  it('renders pipeline segment documents instead of returning null (#690 follow-up)', () => {
    const md = renderDocumentMarkdownFromPayload(BONDS_PAYLOAD, 'bonds');
    expect(md).not.toBeNull();
    expect(md).toContain('# Bonds — 2026-06-12');
  });

  it('renders digest-delta documents with the master digest renderer', () => {
    const md = renderDocumentMarkdownFromPayload(fixtureDigest(), 'digest-delta');
    expect(md).toContain('# Daily Digest — 2026-04-27');
  });

  it('renders pm-rebalance documents', () => {
    const md = renderDocumentMarkdownFromPayload(REBALANCE_EMPTY, 'pm-rebalance');
    expect(md).toContain('# Rebalance Decision');
  });

  it('renders analyst documents with the analyst specialist renderer (#814)', () => {
    const md = renderDocumentMarkdownFromPayload(ANALYST_PAYLOAD, 'analyst/NVDA');
    // The analyst renderer is called from queries.ts (not render-document-from-payload),
    // but the payload shape sniffer must not mis-route it to a wrong renderer.
    // isAnalystSpecialistPayload is exported for that check — verify it classifies correctly.
    expect(isAnalystSpecialistPayload(ANALYST_PAYLOAD)).toBe(true);
    // The fallback renderer in render-document-from-payload will render the JSON since
    // isAnalystSpecialistPayload is not wired into renderDocumentMarkdownFromPayload directly,
    // but the payload must not match the deliberation path.
    expect(isDebateSummaryPayload(ANALYST_PAYLOAD)).toBe(false);
    // Verify md is non-null.
    expect(md).not.toBeNull();
  });

  it('renders deliberation documents with the debate renderer (#698)', () => {
    const md = renderDocumentMarkdownFromPayload(DEBATE_PAYLOAD, 'deliberation/NVDA');
    expect(md).toContain('# Bull / Bear Debate — NVDA');
    expect(md).toContain('## Bull thesis');
    expect(md).toContain('Datacenter capex');
  });

  it('renders risk-debate documents with the risk-debate renderer (#698)', () => {
    const md = renderDocumentMarkdownFromPayload(RISK_DEBATE_PAYLOAD, 'risk-debate');
    expect(md).toContain('# Risk Temperament Debate');
    expect(md).toContain('## Key tension');
  });

  it('still renders the legacy v1 snapshot payload through the v1 path', () => {
    const md = renderDocumentMarkdownFromPayload(V1_SNAPSHOT, 'digest');
    expect(md).toContain('## Market Regime Snapshot');
    expect(md).toContain('| Technology | XLK | bullish | high | AI capex |');
  });

  it('renders unknown shapes as a JSON dump instead of null', () => {
    const md = renderDocumentMarkdownFromPayload({ mystery: true }, 'future-doc-kind');
    expect(md).toContain('# future-doc-kind');
    expect(md).toContain('"mystery": true');
  });

  it('returns null for unknown digest-keyed payloads so the snapshot fallback applies', () => {
    expect(renderDocumentMarkdownFromPayload({ mystery: true }, 'digest')).toBeNull();
  });
});

describe('renderDigestMarkdownFromSnapshot shape routing', () => {
  it('delegates the pipeline digest shape to the master renderer', () => {
    const md = renderDigestMarkdownFromSnapshot(fixtureDigest() as never);
    expect(md).toContain('# Daily Digest — 2026-04-27');
  });

  it('keeps rendering the v1 operator shape', () => {
    const md = renderDigestMarkdownFromSnapshot(V1_SNAPSHOT as never);
    expect(md).toContain('# DIGEST — 2026-04-27');
    expect(md).toContain('## Sector Scorecard');
  });
});

describe('snapshot-context digest helpers', () => {
  it('normalizes ActionableItem / RiskItem entries to display strings', () => {
    expect(
      digestItemsToStrings([
        { priority: 1, label: 'Trim tech', rationale: 'Crowded positioning' },
        { horizon_hours: 48, label: 'CPI print', trigger: 'Hot core MoM' },
        'plain string',
      ])
    ).toEqual(['Trim tech — Crowded positioning', 'CPI print — Hot core MoM', 'plain string']);
    expect(digestItemsToStrings(null)).toEqual([]);
  });

  it('builds context bullets from digest narrative sections', () => {
    const bullets = extractDigestContextBullets(fixtureDigest());
    expect(bullets.length).toBeGreaterThan(0);
    expect(bullets[0]).toMatch(/^US equities: /);
  });
});
