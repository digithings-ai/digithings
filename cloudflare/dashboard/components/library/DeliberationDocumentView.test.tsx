import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import DeliberationDocumentView, {
  extractPmAnalystTranscript,
  shouldShowDistinctTheses,
} from './DeliberationDocumentView';

/** Production-shaped DBO payload (2026-08-27): chat turns under `rounds`, theses = conclusion. */
const DBO_H6_PAYLOAD = {
  ticker: 'DBO',
  net_stance: 'neutral',
  conviction_delta: 0,
  converged: true,
  carried: false,
  conclusion:
    'All three PM challenges are accepted. The original payload was inadequate: conviction 0 on a non-held ticker with a played-out thesis is a non-call.',
  bull_thesis:
    'All three PM challenges are accepted. The original payload was inadequate: conviction 0 on a non-held ticker with a played-out thesis is a non-call.',
  bear_thesis:
    'All three PM challenges are accepted. The original payload was inadequate: conviction 0 on a non-held ticker with a played-out thesis is a non-call.',
  rounds: [
    {
      role: 'pm',
      round_number: 1,
      message: 'Three challenges:\n\n1. **Conviction 0 on a non-held ticker is a non-call.**',
    },
    {
      role: 'analyst',
      round_number: 1,
      message: '## Response to PM Challenges\n\n### Challenge 1\n**Accepted.** Recommend COMPLETED.',
    },
  ],
  rounds_count: 1,
};

const LEGACY_BULL_BEAR = {
  ticker: 'NVDA',
  net_stance: 'bullish',
  conviction_delta: 1,
  bull_thesis: 'Datacenter capex supercycle intact.',
  bear_thesis: 'Multiple compression risk on any guide-down.',
  rounds: [
    {
      round_number: 1,
      bull_argument: 'AI demand accelerating',
      bear_argument: 'Valuation stretched',
    },
  ],
};

describe('DeliberationDocumentView H6 chat mapping', () => {
  it('extracts PM↔analyst turns from rounds when transcript is absent', () => {
    const turns = extractPmAnalystTranscript(DBO_H6_PAYLOAD);
    expect(turns).toHaveLength(2);
    expect(turns[0]?.role).toBe('pm');
    expect(turns[1]?.role).toBe('analyst');
  });

  it('hides bull/bear cards when both theses mirror the conclusion', () => {
    expect(
      shouldShowDistinctTheses({
        bullThesis: DBO_H6_PAYLOAD.bull_thesis,
        bearThesis: DBO_H6_PAYLOAD.bear_thesis,
        conclusion: DBO_H6_PAYLOAD.conclusion,
      }),
    ).toBe(false);
  });

  it('renders chat turns and does not show empty Bull/Bear debate rounds', () => {
    const html = renderToStaticMarkup(
      createElement(DeliberationDocumentView, {
        payload: DBO_H6_PAYLOAD,
        fallbackMarkdown: '# Fallback',
        docDate: '2026-08-27',
      }),
    );
    expect(html).toContain('data-testid="deliberation-chat"');
    expect(html).toContain('Conviction 0 on a non-held ticker is a non-call');
    expect(html).toContain('Response to PM Challenges');
    // Must not treat chat turns as empty bull/bear round cards
    expect(html).not.toContain('Debate rounds');
    expect(html).not.toContain('Bull thesis');
    expect(html).not.toContain('Bear thesis');
  });

  it('opens with the H5 analyst report, then role-labeled bubbles without Round N titles', () => {
    const html = renderToStaticMarkup(
      createElement(DeliberationDocumentView, {
        payload: DBO_H6_PAYLOAD,
        fallbackMarkdown: '# Fallback',
        docDate: '2026-08-27',
      }),
    );
    const h5Idx = html.indexOf('data-testid="deliberation-h5-report"');
    const chatIdx = html.indexOf('data-testid="deliberation-chat"');
    expect(h5Idx).toBeGreaterThanOrEqual(0);
    expect(chatIdx).toBeGreaterThan(h5Idx);
    expect(html).toContain('DBO analyst report');
    expect(html).toMatch(/analyst(%2F|\/)DBO/);
    expect(html).toContain('data-role="pm"');
    expect(html).toContain('data-role="analyst"');
    expect(html).not.toContain('Round 1');
    expect(html).not.toContain('>Conclusion<');
    expect(html).not.toContain('>Conclusion</');
  });

  it('shows Conclusion only when the transcript is empty (carry)', () => {
    const html = renderToStaticMarkup(
      createElement(DeliberationDocumentView, {
        payload: {
          ticker: 'SHY',
          net_stance: 'neutral',
          conclusion: 'Prior agreement still stands.',
          carried: true,
          carry_reason: 'fingerprint_skip',
          converged: true,
          rounds: [],
        },
        fallbackMarkdown: '',
        docDate: '2026-08-27',
      }),
    );
    expect(html).toContain('Conclusion');
    expect(html).toContain('Prior agreement still stands');
  });

  it('still renders legacy bull/bear debate summaries', () => {
    const html = renderToStaticMarkup(
      createElement(DeliberationDocumentView, {
        payload: LEGACY_BULL_BEAR,
        fallbackMarkdown: '',
      }),
    );
    expect(html).toContain('Bull thesis');
    expect(html).toContain('Datacenter capex');
    expect(html).toContain('Debate rounds');
    expect(html).toContain('AI demand accelerating');
  });

  it('shows an honest empty-chat note for carried debates without turns', () => {
    const html = renderToStaticMarkup(
      createElement(DeliberationDocumentView, {
        payload: {
          ticker: 'SHY',
          net_stance: 'neutral',
          conclusion: 'Prior agreement still stands.',
          carried: true,
          carry_reason: 'fingerprint_skip',
          converged: true,
          bull_thesis: 'Prior agreement still stands.',
          bear_thesis: 'Prior agreement still stands.',
          rounds: [],
        },
        fallbackMarkdown: '',
      }),
    );
    expect(html).toContain('data-testid="deliberation-no-chat"');
    expect(html).toContain('fingerprint_skip');
    expect(html).not.toContain('Bull thesis');
  });
});
