import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, it, expect, vi } from 'vitest';

let search = '';
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
}));

// The live lane is stubbed rather than driven: these are `renderToStaticMarkup` tests, so no
// effect ever runs and the real hook could only ever return an empty map. The hook itself
// (seed + realtime + coalescing) is covered in lib/; what matters here is what the table
// renders for a given quote — and that a MISSING quote falls back to the close (#1833).
let liveQuotes: Record<string, LiveQuote> = {};
vi.mock('@/lib/hooks/use-live-prices', () => ({
  useLivePrices: () => liveQuotes,
}));

import AllocationsPositionsTable from './AllocationsPositionsTable';
import type { BookReconciliation, ReconciledPosition } from '@/lib/book-reconciliation';
import type { LiveQuote } from '@/lib/live-valuation';

function pos(over: Partial<ReconciledPosition>): ReconciledPosition {
  return {
    ticker: 'NVDA', name: 'NVIDIA Corporation', type: 'LONG', weight_actual: 30, weight_target: null,
    weight_delta: null, current_price: 100, entry_price: 90, entry_date: null, rationale: '',
    thesis_ids: [], category: 'equity', pm_notes: '', stats: {}, normalizedWeight: 22.5,
    conviction: 3, sector_bucket: 'Technology', stop_loss_pct: -8, target_pct_gain: 15,
    horizon_days: 30, day_change_pct: 1.2, unrealized_pnl_pct: 11.1, ...over,
  };
}
const recon = (rows: ReconciledPosition[]): BookReconciliation => ({
  rows, investedPct: 75, cashPct: 25, grossPct: 75, netPct: 75,
});

/** `quoted_at` — the exchange tick time, canonical ISO as the hook hands it over. */
const QUOTED_AT = '2026-08-03T18:23:00.000Z';
/** `metrics_as_of` — when the nightly close-keyed batch last wrote the record. */
const METRICS_AS_OF = '2026-08-01T20:05:00+00:00';
/**
 * The default reference instant — one minute after {@link QUOTED_AT}, i.e. a fresh quote.
 *
 * Injected as a prop so these assertions test the LABEL RULE and not the machine clock: with
 * the real `Date.now()`, every fixture below would age into staleness the day after it was
 * written and the suite would start failing on the calendar.
 */
const FRESH_NOW = Date.parse(QUOTED_AT) + 60_000;
/** Past the five-minute threshold by hours — the production reading of 2026-08-04. */
const STALE_NOW = Date.parse(QUOTED_AT) + 18.63 * 3_600_000;

/** One row rendered with the current `liveQuotes` stub; entry 90 / close 100 unless overridden. */
function row(over: Partial<ReconciledPosition> = {}, nowMs: number = FRESH_NOW): string {
  return renderToStaticMarkup(createElement(AllocationsPositionsTable, {
    reconciliation: recon([
      pos({ entry_price: 90, current_price: 100, unrealized_pnl_pct: 11.1, metrics_as_of: METRICS_AS_OF, ...over }),
    ]),
    nowMs,
  }));
}

/**
 * Markup with structural test hooks stripped, for assertions about the WORD the reader sees.
 * `data-live-mark` is RiskEnvelopeCell's targeting attribute and contains "live" whatever the
 * label says, so it would silently satisfy a `not.toContain('live')` check.
 */
const visibleText = (html: string): string => html.replace(/data-live-mark=""/g, '');

describe('AllocationsPositionsTable', () => {
  beforeEach(() => {
    search = '';
    liveQuotes = {};
  });

  it('renders normalized weights (not raw 150%-summing weight_actual)', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({ normalizedWeight: 22.5 })]),
    }));
    expect(html).toContain('22.5%');
    expect(html).not.toContain('30.0%');
  });

  it('shows the category directly in each position row', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({ ticker: 'XLY', category: 'sector-consumer-disc' })]),
    }));
    expect(html).toContain('Consumer discretionary');
    expect(html).not.toContain('Sector-Consumer-Disc');
  });

  it('identifies each ticker with its canonical official name', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({ ticker: 'NVDA', name: 'NVIDIA Corporation' })]),
    }));
    expect(html).toContain('NVDA');
    expect(html).toContain('NVIDIA Corporation');
    expect(html).toContain('title="NVIDIA Corporation"');
  });

  it('keeps only inventory, allocation, risk-envelope, and dossier columns', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({})]),
    }));
    expect(html).not.toContain('>Name<');
    expect(html).toContain('>Holding<');
    expect(html).toContain('>Category<');
    expect(html).toContain('>Weight / target<');
    expect(html).toContain('>Stop ↔ target<');
    expect(html).not.toContain('>Conviction<');
    expect(html).not.toContain('>Day<');
    expect(html).not.toContain('>Unrealized<');
  });

  it('uses the ticker dossier as the only row follow-through', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({ ticker: 'NVDA' })]),
    }));
    expect(html).toContain('/portfolio/tickers?ticker=NVDA');
    expect(html).not.toContain('/pipeline?');
    expect(html).not.toContain('Decision');
  });

  it('uses no off-palette blue/purple literals', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({})]),
    }));
    expect(html).not.toContain('59,130,246');
    expect(html).not.toContain('a78bfa');
  });

  it('highlights a mixed-case ticker targeted by a deep link without expanding it', () => {
    search = 'ticker=nvda';
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({ ticker: 'Nvda' })]),
    }));
    expect(html).toContain('data-selected="true"');
    expect(html).not.toContain('Avg entry');
  });

  it('uses canonical compact text on category and dossier link', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({})]),
    }));
    expect(html).toContain('text-xs text-ink-soft');
    expect(html).toContain('Dossier');
  });

  it('uses squared flat hairline ledger treatment instead of glass-card', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({})]),
    }));
    expect(html).not.toContain('glass-card');
    expect(html).not.toContain('rounded-lg');
    expect(html).toContain('border-hair');
  });

  it('has semantic structural selectors for test targeting', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({})]),
    }));
    expect(html).toContain('data-region="positions-table"');
    expect(html).toContain('table-fixed');
    expect(html).toContain('sticky top-0');
    expect(html).not.toContain('min-w-[980px]');
  });

  // #1833 — the live valuation overlay. Two layers that must not merge: the close-keyed record
  // stays what the nightly batch wrote; the figure below is derived in the browser and stored
  // nowhere. Attribution is part of the feature — a live figure and a close figure that render
  // identically leave the reader unable to tell current from stale.
  it('values a holding from the live quote, not from the close-keyed record', () => {
    liveQuotes = { NVDA: { price: 120, changePct: 1.24, quotedAt: QUOTED_AT } };
    const html = row({ ticker: 'NVDA' });
    expect(html).toContain('+33.3%'); // (120 − 90) / 90, from prices_live
    expect(html).toContain('>live<');
    expect(html).toContain('quoted 18:23 UTC on 2026-08-03');
    expect(html).not.toContain('+11.1%'); // the persisted close-to-close number is not shown
    expect(html).not.toContain('+1.2%'); // nor is change-vs-prior-close, a different quantity
  });

  it('falls back to the close and labels it as a close when the ticker has no live coverage', () => {
    liveQuotes = {}; // the publisher caps at 25 symbols — a held ticker may simply be absent
    const html = row({ ticker: 'NVDA' });
    expect(html).toContain('+11.1%');
    expect(html).toContain('>close<');
    expect(html).toContain('official close of 2026-08-01');
    expect(html).not.toContain('>live<');
  });

  it('treats a halted zero-price quote as no quote and shows the close instead', () => {
    liveQuotes = { NVDA: { price: 0, changePct: null, quotedAt: QUOTED_AT } };
    const html = row({ ticker: 'NVDA' });
    expect(html).toContain('>close<');
    expect(html).toContain('+11.1%'); // the close, positively — not merely "no live figure"
    expect(html).not.toContain('100.0%'); // a 0 mark would read as down ~100%
  });

  it('renders the empty convention — never a zero — when neither lane has a mark', () => {
    const html = row({ current_price: null, unrealized_pnl_pct: null, metrics_as_of: null });
    expect(html).toContain('—');
    expect(html).not.toContain('0.0%');
    expect(html).not.toContain('>live<');
    expect(html).not.toContain('>close<');
    expect(html).toContain('no live quote and no closing mark');
  });

  it('carries the source and timestamp to assistive tech, not by colour alone', () => {
    liveQuotes = { NVDA: { price: 120, changePct: 1.24, quotedAt: QUOTED_AT } };
    const html = row({ ticker: 'NVDA' });
    expect(html).toContain(
      'NVDA: +33.3% since entry, from a live quote, quoted 18:23 UTC on 2026-08-03.'
    );
    expect(html).toContain('title="Live');
    // The visible label is a word, so the attribution survives monochrome and colour blindness.
    expect(html).toContain('>live<');
  });

  it('drives the risk-envelope marker from the same valuation', () => {
    liveQuotes = { NVDA: { price: 94.5, changePct: 0.4, quotedAt: QUOTED_AT } };
    const html = row({ ticker: 'NVDA', stop_loss_pct: -8, target_pct_gain: 15 });
    expect(html).toContain('data-live-mark');
    expect(html).toContain('inside the stop-to-target range');
  });

  it('leaves the risk-envelope marker off a row with no mark to place', () => {
    const html = row({ current_price: null, unrealized_pnl_pct: null, metrics_as_of: null });
    expect(html).not.toContain('data-live-mark');
  });

  // #1833 — the freshness gate. `prices_live` rows persist indefinitely: the publisher only
  // upserts (no DELETE path, migration 063) and is idle outside 13:00–01:00 UTC Mon–Fri, so a
  // row is present all night, all weekend and right through a per-ticker feed freeze. Presence
  // is provenance; only `quoted_at` can license the word "live".
  it('drops the word "live" once the quote is past the threshold, keeping the figure', () => {
    liveQuotes = { NVDA: { price: 120, changePct: 1.24, quotedAt: QUOTED_AT } };
    const html = row({ ticker: 'NVDA' }, STALE_NOW);
    // The value is unchanged — the live mark is still the best one available.
    expect(html).toContain('+33.3%');
    expect(html).not.toContain('+11.1%'); // still not the close-keyed record
    // But nothing in the row claims currency, in any of the three places attribution lives.
    expect(visibleText(html)).not.toMatch(/live/i);
    expect(html).toContain('>stale 18h<');
    // The instant replaces the claim, and stays reachable without colour.
    expect(html).toContain('quoted 18:23 UTC on 2026-08-03');
    expect(html).toContain('NVDA: +33.3% since entry, from a quote that has not advanced in 18h');
    expect(html).toContain('title="Stale quote');
  });

  it('flips exactly at the threshold: fresh at 5m, stale one millisecond later', () => {
    liveQuotes = { NVDA: { price: 120, changePct: 1.24, quotedAt: QUOTED_AT } };
    const at = Date.parse(QUOTED_AT) + 5 * 60 * 1000;
    expect(row({ ticker: 'NVDA' }, at)).toContain('>live<');
    const past = row({ ticker: 'NVDA' }, at + 1);
    expect(past).not.toContain('>live<');
    expect(past).toContain('>stale 5m<');
  });

  it('labels freshness PER TICKER — one frozen symbol beside a ticking one, same render', () => {
    // The measured case a global "is the market open?" check would miss entirely: both rows are
    // mid-session and both have a `prices_live` row; only their own `quoted_at` differs.
    const at = Date.parse('2026-08-04T20:00:00.000Z');
    liveQuotes = {
      NVDA: { price: 120, changePct: 1.2, quotedAt: '2026-08-04T19:59:30.000Z' },
      TLT: { price: 94.5, changePct: -0.1, quotedAt: '2026-08-04T15:08:00.000Z' },
    };
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([
        pos({ ticker: 'NVDA', name: 'NVIDIA Corporation', normalizedWeight: 30, entry_price: 90, current_price: 100, unrealized_pnl_pct: 11.1, metrics_as_of: METRICS_AS_OF }),
        pos({ ticker: 'TLT', name: 'iShares 20+ Year Treasury', normalizedWeight: 10, entry_price: 90, current_price: 100, unrealized_pnl_pct: 11.1, metrics_as_of: METRICS_AS_OF }),
      ]),
      nowMs: at,
    }));
    // One render, two verdicts: NVDA (30s old) live, TLT (4h52m old) stale with its age.
    expect(html).toContain('>live<');
    expect(html).toContain('>stale 4h<');
    expect(html).toContain('NVDA: +33.3% since entry, from a live quote');
    expect(html).toContain('TLT: +5.0% since entry, from a quote that has not advanced in 4h');
    // And the stale row's own risk-envelope label does not inherit the neighbour's claim.
    expect(html).toContain('Now +5.0% vs entry on a quote 4h old');
    expect(html).toContain('Now +33.3% vs entry live');
  });

  it('reads the reference instant from the prop, so the label is not clock-dependent', () => {
    liveQuotes = { NVDA: { price: 120, changePct: 1.24, quotedAt: QUOTED_AT } };
    // Same fixture, same quote, two instants — the only thing that moves is the word. This is
    // what keeps lib/live-valuation.ts free of a clock read.
    expect(row({ ticker: 'NVDA' }, FRESH_NOW)).toContain('>live<');
    expect(row({ ticker: 'NVDA' }, STALE_NOW)).toContain('>stale 18h<');
  });

  it('never calls the nightly close a stale quote, however recently it was written', () => {
    liveQuotes = {}; // no live coverage: the close carries the row
    const html = row({ ticker: 'NVDA' }, Date.parse(METRICS_AS_OF) + 1_000);
    expect(html).toContain('>close<');
    expect(html).not.toContain('stale');
    expect(visibleText(html)).not.toMatch(/live/i);
  });

  it('keeps target weight beside current weight instead of adding a wide column', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      reconciliation: recon([pos({ weight_target: 20 })]),
    }));
    expect(html).toContain('22.5%');
    expect(html).toContain('20.0% target');
    expect(html.match(/<col/g)).toHaveLength(6); // colgroup plus five columns
  });

  // #1850: the owner's rule — show +/- for an add or a trim, but a brand-new or removed position
  // has no rate of change, so nothing is shown rather than a fabricated 0.0pp or full-size delta.
  describe('weight-change badge', () => {
    // Signed percentage-point badge, e.g. "+5.1pp" / "\u22124.9pp". Matched by shape because a
    // bare 'pp' substring occurs elsewhere in the markup.
    const BADGE = /[+\u2212-]\d+\.\d+pp/;

    it('shows a signed delta for a trim', () => {
      expect(row({ weight_delta: -4.8616 })).toContain('4.9pp');
    });

    it('shows a plus for an add', () => {
      const html = row({ weight_delta: 5.0793 });
      expect(html).toContain('+');
      expect(html).toContain('5.1pp');
    });

    it('renders nothing for a brand-new or removed position', () => {
      // weight_delta is null in exactly those cases (lib/holding-weight-change.ts).
      expect(row({ weight_delta: null })).not.toMatch(BADGE);
    });

    it('renders nothing for a hold that did not move', () => {
      expect(row({ weight_delta: 0 })).not.toMatch(BADGE);
    });

    it('does not colour the badge with P&L tokens', () => {
      // tokens.css reserves --up/--down for P&L; a position getting bigger is not a gain, and
      // HoldingsActivityTable's weight-change column is neutral for the same reason.
      const html = row({ weight_delta: 5.0793 });
      const badge = html.slice(html.indexOf('5.1pp') - 260, html.indexOf('5.1pp'));
      expect(badge).not.toContain('text-up');
      expect(badge).not.toContain('text-down');
    });
  });
});
