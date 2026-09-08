import { describe, expect, it } from 'vitest';
import {
  buildIdeaDetailModel,
  formatLevelValue,
  formatRiskReward,
  hasTradeLevels,
  pairPriceDecimals,
  parseEvidence,
  parseTradeLevels,
  provenanceChipLabel,
  evidenceStanceClass,
} from './trade-levels';
import type { FxTradeIdeaRow, FxTradeLevel } from './types';

const computed: FxTradeLevel = {
  value: '1.14',
  provenance: 'computed',
  source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
};

const broker: FxTradeLevel = {
  value: '1.18',
  provenance: 'broker_quoted',
  source_ref: 'ING.pdf',
};

describe('parseTradeLevels', () => {
  it('returns null for empty object', () => {
    expect(parseTradeLevels({})).toBeNull();
  });

  it('parses a complete payload', () => {
    const tl = parseTradeLevels({
      entry_low: { value: '1.15', provenance: 'computed', source_ref: computed.source_ref },
      entry_high: { value: '1.16', provenance: 'broker_quoted', source_ref: 'ING.pdf' },
      stop: computed,
      targets: [broker],
      risk_reward: 1.5,
      status: 'complete',
    });
    expect(tl?.status).toBe('complete');
    expect(tl?.targets).toHaveLength(1);
    expect(hasTradeLevels(tl)).toBe(true);
  });
});

describe('provenanceChipLabel', () => {
  it('labels broker PDFs', () => {
    expect(provenanceChipLabel(broker)).toBe('ING target');
  });

  it('labels computed vol refs', () => {
    expect(provenanceChipLabel(computed)).toBe('computed, 1.5×20d vol off 31 Jul fix');
  });

  it('labels bank trade', () => {
    expect(
      provenanceChipLabel({
        value: '1.14',
        provenance: 'pmt_bank_trade',
        source_ref: 'snap:1',
      }),
    ).toBe('bank trade');
  });
});

describe('parseEvidence + stance class', () => {
  it('keeps valid evidence rows', () => {
    const rows = parseEvidence([
      {
        source_slug: 'dmx-overview',
        instrument: 'EUR/USD',
        as_of: '2026-08-01T00:00:00Z',
        statement: 'Retail 73% short EUR/USD',
        stance: 'supports',
        snapshot_id: '00000000-0000-0000-0000-000000000001',
      },
    ]);
    expect(rows).toHaveLength(1);
    expect(evidenceStanceClass('supports')).toContain('accent');
    expect(evidenceStanceClass('contradicts')).toContain('warn');
  });

  it('drops malformed rows', () => {
    expect(parseEvidence([{ statement: 'x' }])).toEqual([]);
  });
});

describe('formatLevelValue + pair decimals', () => {
  it('trims broker trailing zeros without changing significant digits', () => {
    expect(formatLevelValue('1.1500', 'EUR/USD', 'broker_quoted')).toBe('1.15');
    expect(formatLevelValue('1.3560', 'GBP/USD', 'broker_quoted')).toBe('1.356');
    expect(formatLevelValue('148.50', 'USD/JPY', 'broker_quoted')).toBe('148.5');
  });

  it('rounds computed levels to pair-reasonable decimals', () => {
    expect(pairPriceDecimals('USD/JPY')).toBe(3);
    expect(pairPriceDecimals('EUR/USD')).toBe(5);
    expect(formatLevelValue('148.501234', 'USD/JPY', 'computed')).toBe('148.501');
    expect(formatLevelValue('1.08501234', 'EUR/USD', 'computed')).toBe('1.08501');
  });

  it('formats R:R to one decimal', () => {
    expect(formatRiskReward(1.5)).toBe('1.5');
    expect(formatRiskReward(1.666)).toBe('1.7');
  });
});

const LEVELS_IDEA: FxTradeIdeaRow = {
  run_date: '2026-07-22',
  rank: 1,
  pair: 'USD/JPY',
  direction: 'short',
  title: 'JPY SHORT — via USD/JPY',
  thesis: 'BoJ normalization path repricing.',
  catalyst: 'BoJ minutes Thursday',
  levels: [],
  citations: [{ broker: 'Desk Alpha' }],
  as_of: '2026-07-22T10:00:00Z',
  trade_levels: {
    entry_low: {
      value: '1.15',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    entry_high: {
      value: '1.16',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    stop: {
      value: '1.14',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    targets: [{ value: '1.18', provenance: 'broker_quoted', source_ref: 'ING.pdf' }],
    risk_reward: 1.5,
    status: 'partial',
  },
  evidence: [
    {
      source_slug: 'dmx-overview',
      instrument: 'USD/JPY',
      as_of: '2026-08-01T00:00:00Z',
      statement: 'Retail 78% long USD/JPY',
      stance: 'contradicts',
      snapshot_id: '00000000-0000-0000-0000-000000000002',
    },
  ],
};

describe('buildIdeaDetailModel', () => {
  it('orders short ladder Stop → Entry → Target with roles', () => {
    const model = buildIdeaDetailModel(LEVELS_IDEA);
    expect(model.status).toBe('partial');
    expect(model.riskReward).toBe(1.5);
    expect(model.riskRewardLabel).toBe('1.5');
    expect(model.levelRows.map((r) => r.role)).toEqual(['stop', 'entry', 'target']);
    expect(model.levelRows).toEqual([
      {
        label: 'Stop',
        value: '1.14',
        chip: 'computed, 1.5×20d vol off 31 Jul fix',
        role: 'stop',
      },
      {
        label: 'Entry',
        value: '1.15–1.16',
        chip: 'computed, 1.5×20d vol off 31 Jul fix',
        role: 'entry',
      },
      {
        label: 'Target',
        value: '1.18',
        chip: 'ING target',
        role: 'target',
      },
    ]);
    expect(model.evidenceRows).toHaveLength(1);
    expect(model.evidenceRows[0].statement).toBe('Retail 78% long USD/JPY');
    expect(model.evidenceRows[0].stance).toBe('contradicts');
    expect(model.evidenceRows[0].className).toContain('warn');
  });

  it('orders long ladder Target → Entry → Stop', () => {
    const model = buildIdeaDetailModel({
      ...LEVELS_IDEA,
      pair: 'EUR/USD',
      direction: 'long',
    });
    expect(model.levelRows.map((r) => r.role)).toEqual(['target', 'entry', 'stop']);
  });

  it('sorts multi-target rows price-descending for display', () => {
    const model = buildIdeaDetailModel({
      ...LEVELS_IDEA,
      pair: 'EUR/USD',
      direction: 'long',
      trade_levels: {
        ...LEVELS_IDEA.trade_levels!,
        targets: [
          { value: '1.17', provenance: 'broker_quoted', source_ref: 'low.pdf' },
          { value: '1.20', provenance: 'broker_quoted', source_ref: 'high.pdf' },
          { value: '1.18', provenance: 'broker_quoted', source_ref: 'mid.pdf' },
        ],
      },
    });
    const targets = model.levelRows.filter((r) => r.role === 'target');
    expect(targets.map((r) => r.value)).toEqual(['1.2', '1.18', '1.17']);
    expect(targets.map((r) => r.label)).toEqual(['Target', 'Target 2', 'Target 3']);
  });

  it('returns empty blocks when trade_levels and evidence are absent', () => {
    const model = buildIdeaDetailModel({
      run_date: '2026-07-22',
      rank: 1,
      pair: 'EUR/USD',
      direction: 'long',
      title: 'EUR grind higher',
      thesis: 'Rate differential compression.',
      catalyst: 'ECB speakers',
      levels: [],
      citations: [],
      as_of: '2026-07-22T10:00:00Z',
    });
    expect(model.status).toBeNull();
    expect(model.riskReward).toBeNull();
    expect(model.riskRewardLabel).toBeNull();
    expect(model.levelRows).toEqual([]);
    expect(model.evidenceRows).toEqual([]);
  });
});
