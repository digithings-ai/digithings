import { describe, expect, it } from 'vitest';
import { parseAnalystPayload } from './queries';

describe('parseAnalystPayload (#1562 PR2)', () => {
  it('maps the full H5 AnalystPayload shape verbatim, including a signed conviction_score', () => {
    const payload = parseAnalystPayload({
      ticker: 'qqq',
      conviction_score: -3,
      stance: 'sell',
      thesis: 'Tech is rolling over.',
      risks: 'A rate cut reverses the rotation.',
      sources: ['https://example.com/a', 'https://example.com/b'],
      fundamentals: 'Rich multiples.',
      technicals: 'Below the 50dma.',
      headwinds: ['Regulatory overhang'],
      tailwinds: ['AI capex'],
      bull_case: 'Earnings beat.',
      bear_case: 'Guidance cut.',
      price_targets: { base_case: 302, bear_case: 280, bull_case: 320 },
      expectations: 'Chop into earnings.',
      fingerprint_news_hash: 'abc123',
    });
    expect(payload).toEqual({
      ticker: 'QQQ',
      conviction_score: -3,
      stance: 'sell',
      thesis: 'Tech is rolling over.',
      risks: 'A rate cut reverses the rotation.',
      sources: ['https://example.com/a', 'https://example.com/b'],
      fundamentals: 'Rich multiples.',
      technicals: 'Below the 50dma.',
      headwinds: ['Regulatory overhang'],
      tailwinds: ['AI capex'],
      bull_case: 'Earnings beat.',
      bear_case: 'Guidance cut.',
      price_targets: { base_case: 302, bear_case: 280, bull_case: 320 },
      expectations: 'Chop into earnings.',
      evidence: null,
      fingerprint_news_hash: 'abc123',
    });
  });

  it('tolerates the frozen empty-string / null-price_targets shape seen live (analyst/XLE 06-26)', () => {
    const payload = parseAnalystPayload({
      ticker: 'XLE',
      stance: 'hold',
      thesis: '',
      sources: [],
      headwinds: [],
      tailwinds: [],
      price_targets: null,
      conviction_score: 2,
    });
    expect(payload?.thesis).toBe('');
    expect(payload?.price_targets).toBeNull();
    expect(payload?.conviction_score).toBe(2);
  });

  it('never clamps a signed conviction_score outside 0..5 (−5..+5 per the backend contract)', () => {
    const payload = parseAnalystPayload({ ticker: 'USO', conviction_score: -5, stance: 'sell' });
    expect(payload?.conviction_score).toBe(-5);
  });

  it('returns null for a non-object / missing payload rather than throwing', () => {
    expect(parseAnalystPayload(null)).toBeNull();
    expect(parseAnalystPayload(undefined)).toBeNull();
    expect(parseAnalystPayload('not an object')).toBeNull();
    expect(parseAnalystPayload([])).toBeNull();
  });

  it('defaults missing string/array fields instead of surfacing undefined', () => {
    const payload = parseAnalystPayload({ ticker: 'IWM' });
    expect(payload).toMatchObject({
      ticker: 'IWM',
      conviction_score: 0,
      stance: '',
      thesis: '',
      sources: [],
      headwinds: [],
      tailwinds: [],
      price_targets: null,
    });
  });
});
