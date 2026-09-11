import { describe, it, expect } from 'vitest';
import {
  parseActionableItems,
  parseRiskItems,
  extractMarkdownH2Section,
  parseHeadlineFromDigestBody,
  parseWatchlistFromDigestBody,
  parseRiskRadarFromDigestBody,
  resolveBriefFieldsFromDigest,
} from './snapshot-context';

describe('parseActionableItems', () => {
  it('maps structured items and sorts by priority ascending (null last)', () => {
    const out = parseActionableItems([
      { label: 'Trim XLI', priority: 2, rationale: 'rolling over' },
      { label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs' },
      { label: 'Bare', priority: null, rationale: null },
    ]);
    expect(out.map((a) => a.label)).toEqual(['Monitor DXY above 120.4', 'Trim XLI', 'Bare']);
    expect(out[0]).toEqual({
      label: 'Monitor DXY above 120.4',
      priority: 1,
      rationale: 'near YTD highs',
    });
  });
  it('degrades plain-string items and drops empties', () => {
    expect(parseActionableItems(['Hold the book', '', '  '])).toEqual([
      { label: 'Hold the book', priority: null, rationale: null },
    ]);
  });
  it('returns [] for non-array input', () => {
    expect(parseActionableItems(null)).toEqual([]);
    expect(parseActionableItems({})).toEqual([]);
  });
});

describe('parseRiskItems', () => {
  it('maps trigger + horizon_hours, preserves order', () => {
    const out = parseRiskItems([
      { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizon_hours: 48 },
      { label: 'Tail B', trigger: null, horizon_hours: null },
    ]);
    expect(out).toEqual([
      { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizonHours: 48 },
      { label: 'Tail B', trigger: null, horizonHours: null },
    ]);
  });
  it('degrades plain strings and ignores labelless objects', () => {
    expect(parseRiskItems(['liquidity gap', { trigger: 'x' }])).toEqual([
      { label: 'liquidity gap', trigger: null, horizonHours: null },
    ]);
  });
});

/**
 * Real-ish Sep 4 body shape after stitch-to-body (#3641 diagnosis):
 * envelope is thin `{body, date, regime_label, segment, …}` while Brief
 * content lives only under ## Headline / ## Watchlist / ## Risk radar.
 */
const SEP4_BODY_FIXTURE = `# Daily Digest — 2026-09-04

## Headline

Risk-off consolidation holds as dollar strength and sticky yields keep equity
breadth narrow; semis remain the relative bright spot.

## Market regime

Risk-Off Consolidation. Growth leadership is selective; cyclicals lag.

## Watchlist

- **[P1] Monitor DXY above 104.2** — near YTD highs; a clean break risks another equity drawdown leg
- **[P2] Watch semis breadth into earnings** — AI capex commentary still the relative bright spot
- **[P3] Track 10Y yields vs 4.25%** — sticky yields keep duration and growth multiple under pressure
- **[P4] Follow USD/JPY toward 148** — intervention chatter rises if momentum accelerates
- **[P5] Note crude inventory surprise** — energy lagging; inventory miss would extend underperformance

## Risk radar

- **BOJ intervention** — USD/JPY break above 148 _(≤48h)_
- **Hotter core CPI print** — core MoM > 0.3% into the next release _(≤72h)_
- **Equity gap-down on dollar spike** — DXY surge > 0.8% session with VIX > 20

## Alt-data

Card spend flat WoW; cargo throughput soft.
`;

describe('extractMarkdownH2Section', () => {
  it('returns content under a heading until the next ##', () => {
    const watch = extractMarkdownH2Section(SEP4_BODY_FIXTURE, 'Watchlist');
    expect(watch).toContain('[P1] Monitor DXY');
    expect(watch).not.toContain('## Risk radar');
    expect(watch).not.toContain('BOJ intervention');
  });
  it('is case-insensitive on the heading', () => {
    expect(extractMarkdownH2Section(SEP4_BODY_FIXTURE, 'risk radar')).toContain(
      'BOJ intervention',
    );
  });
  it('returns empty string when heading missing', () => {
    expect(extractMarkdownH2Section(SEP4_BODY_FIXTURE, 'Findings')).toBe('');
  });
});

describe('parseHeadlineFromDigestBody', () => {
  it('takes the first paragraph under ## Headline', () => {
    const h = parseHeadlineFromDigestBody(SEP4_BODY_FIXTURE);
    expect(h).toMatch(/^Risk-off consolidation holds/);
    expect(h).toContain('semis remain the relative bright spot.');
    expect(h).not.toContain('## Market regime');
  });
  it('returns null when Headline section absent', () => {
    expect(parseHeadlineFromDigestBody('## Watchlist\n\n- item')).toBeNull();
  });
});

describe('parseWatchlistFromDigestBody', () => {
  it('parses P1–P5 monitor items from Sep 4-shaped body', () => {
    const items = parseWatchlistFromDigestBody(SEP4_BODY_FIXTURE);
    expect(items).toHaveLength(5);
    expect(items[0]).toEqual({
      label: 'Monitor DXY above 104.2',
      priority: 1,
      rationale:
        'near YTD highs; a clean break risks another equity drawdown leg',
    });
    expect(items.map((i) => i.priority)).toEqual([1, 2, 3, 4, 5]);
    expect(items[4]!.label).toBe('Note crude inventory surprise');
  });
  it('handles unbolded [Pn] bullets and bare labels', () => {
    const body = `## Watchlist

- [P2] Second item — rationale two
- Bare monitor only
`;
    const items = parseWatchlistFromDigestBody(body);
    expect(items[0]).toEqual({
      label: 'Second item',
      priority: 2,
      rationale: 'rationale two',
    });
    expect(items[1]).toEqual({
      label: 'Bare monitor only',
      priority: null,
      rationale: null,
    });
  });
});

describe('parseRiskRadarFromDigestBody', () => {
  it('parses label / trigger / horizon from Sep 4-shaped body', () => {
    const risks = parseRiskRadarFromDigestBody(SEP4_BODY_FIXTURE);
    expect(risks).toHaveLength(3);
    expect(risks[0]).toEqual({
      label: 'BOJ intervention',
      trigger: 'USD/JPY break above 148',
      horizonHours: 48,
    });
    expect(risks[1]!.horizonHours).toBe(72);
    expect(risks[2]).toEqual({
      label: 'Equity gap-down on dollar spike',
      trigger: 'DXY surge > 0.8% session with VIX > 20',
      horizonHours: null,
    });
  });
});

describe('resolveBriefFieldsFromDigest', () => {
  it('derives headline / actionables / risks from body-only snapshot', () => {
    const brief = resolveBriefFieldsFromDigest({
      body: SEP4_BODY_FIXTURE,
      date: '2026-09-04',
      regime_label: 'Risk-Off Consolidation',
      segment: 'master-digest',
    });
    expect(brief.headline).toMatch(/^Risk-off consolidation holds/);
    expect(brief.actionableItems).toHaveLength(5);
    expect(brief.riskItems).toHaveLength(3);
    expect(brief.actionable[0]).toContain('Monitor DXY above 104.2');
    expect(brief.risks[0]).toContain('BOJ intervention');
  });

  it('lets structured fields win over markdown parse', () => {
    const brief = resolveBriefFieldsFromDigest({
      body: SEP4_BODY_FIXTURE,
      headline: 'Structured headline wins',
      actionable_summary: [
        { label: 'Structured watch', priority: 1, rationale: 'from JSON' },
      ],
      risk_radar: [
        { label: 'Structured risk', trigger: 'JSON trigger', horizon_hours: 12 },
      ],
    });
    expect(brief.headline).toBe('Structured headline wins');
    expect(brief.actionableItems).toEqual([
      { label: 'Structured watch', priority: 1, rationale: 'from JSON' },
    ]);
    expect(brief.riskItems).toEqual([
      { label: 'Structured risk', trigger: 'JSON trigger', horizonHours: 12 },
    ]);
  });

  it('falls back per-field when structured arrays are empty', () => {
    const brief = resolveBriefFieldsFromDigest({
      body: SEP4_BODY_FIXTURE,
      headline: 'Keep structured headline',
      actionable_summary: [],
      risk_radar: [],
    });
    expect(brief.headline).toBe('Keep structured headline');
    expect(brief.actionableItems).toHaveLength(5);
    expect(brief.riskItems).toHaveLength(3);
  });

  it('returns empty Brief fields for empty digest', () => {
    expect(resolveBriefFieldsFromDigest({})).toEqual({
      headline: null,
      actionableItems: [],
      riskItems: [],
      actionable: [],
      risks: [],
    });
  });
});
