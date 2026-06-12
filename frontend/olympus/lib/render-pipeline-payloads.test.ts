import { describe, expect, it } from 'vitest';
import { fixtureDigest } from './__fixtures__/snapshot-fixture';
import { renderDigestMarkdownFromSnapshot } from './render-digest-from-snapshot';
import { renderDocumentMarkdownFromPayload } from './render-document-from-payload';
import {
  isMasterDigestPayload,
  isRebalancePayload,
  isSegmentReportPayload,
  renderMasterDigestMarkdown,
  renderRebalanceMarkdown,
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
