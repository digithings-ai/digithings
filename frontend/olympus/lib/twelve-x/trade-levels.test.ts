import { describe, expect, it } from 'vitest';
import {
  formatLevelValue,
  hasTradeLevels,
  parseEvidence,
  parseTradeLevels,
  provenanceChipLabel,
  evidenceStanceClass,
} from './trade-levels';
import type { FxTradeLevel } from './types';

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

describe('formatLevelValue', () => {
  it('keeps significant decimals', () => {
    expect(formatLevelValue('1.1500')).toMatch(/^1\.15/);
  });
});
