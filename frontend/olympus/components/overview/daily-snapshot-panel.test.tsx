import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DailySnapshotPanel } from './daily-snapshot-panel';
import {
  fixtureDigest,
  fixtureEnvelope,
} from '@/lib/__fixtures__/snapshot-fixture';
import type { SnapshotFetchResult } from '@/lib/snapshot-types';

const FIXED_NOW = new Date('2026-04-27T12:00:00Z');

function render(node: React.ReactElement): string {
  return renderToStaticMarkup(node);
}

/**
 * `renderToStaticMarkup` HTML-encodes `&`, `<`, `>`, `"`. Tests assert
 * against text content, so apply the same transform before checking.
 */
function htmlEscape(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

describe('DailySnapshotPanel — present envelope', () => {
  const result: SnapshotFetchResult = { kind: 'present', envelope: fixtureEnvelope() };

  it('renders the headline, segment, run_date, and run_type from the envelope', () => {
    const html = render(
      createElement(DailySnapshotPanel, { fetchResult: result, now: FIXED_NOW }),
    );
    const env = fixtureEnvelope();
    expect(html).toContain(htmlEscape(env.digest.headline));
    expect(html).toContain(htmlEscape(env.digest.segment));
    expect(html).toContain(env.run_date);
    expect(html).toContain(env.run_type);
  });

  it('every visible narrative section traces to a digest field', () => {
    const html = render(
      createElement(DailySnapshotPanel, { fetchResult: result, now: FIXED_NOW }),
    );
    const digest = fixtureDigest();
    const narrativeFields = [
      digest.market_regime_snapshot,
      digest.alt_data_dashboard,
      digest.institutional_summary,
      digest.asset_classes_summary,
      digest.us_equities_summary,
      digest.thesis_tracker,
      digest.portfolio_recommendations,
    ];
    for (const slot of narrativeFields) {
      expect(html).toContain(htmlEscape(slot));
    }
  });

  it('renders every actionable summary entry from the envelope', () => {
    const html = render(
      createElement(DailySnapshotPanel, { fetchResult: result, now: FIXED_NOW }),
    );
    for (const item of fixtureDigest().actionable_summary) {
      expect(html).toContain(htmlEscape(item.label));
      expect(html).toContain(htmlEscape(item.rationale));
      expect(html).toContain(`P${item.priority}`);
    }
  });

  it('renders every risk-radar entry from the envelope', () => {
    const html = render(
      createElement(DailySnapshotPanel, { fetchResult: result, now: FIXED_NOW }),
    );
    for (const item of fixtureDigest().risk_radar) {
      expect(html).toContain(htmlEscape(item.label));
      expect(html).toContain(htmlEscape(item.trigger));
      expect(html).toContain(`${item.horizon_hours}h`);
    }
  });

  it('renders the bias label transformed for display', () => {
    const html = render(
      createElement(DailySnapshotPanel, { fetchResult: result, now: FIXED_NOW }),
    );
    // bias 'bullish' renders verbatim; multi-word ones replace underscores.
    expect(html).toContain('bullish');
  });

  it('does not show the stale banner when published_at is fresh', () => {
    const fresh: SnapshotFetchResult = {
      kind: 'present',
      envelope: { ...fixtureEnvelope(), published_at: FIXED_NOW.toISOString() },
    };
    const html = render(
      createElement(DailySnapshotPanel, { fetchResult: fresh, now: FIXED_NOW }),
    );
    expect(html).not.toContain('snapshot-stale-banner');
    expect(html).not.toContain('Stale snapshot');
  });

  it('shows the stale banner when published_at is older than 48h', () => {
    const stalePublished = new Date(FIXED_NOW.getTime() - 72 * 60 * 60 * 1000).toISOString();
    const stale: SnapshotFetchResult = {
      kind: 'present',
      envelope: { ...fixtureEnvelope(), published_at: stalePublished },
    };
    const html = render(
      createElement(DailySnapshotPanel, { fetchResult: stale, now: FIXED_NOW }),
    );
    expect(html).toContain('snapshot-stale-banner');
    expect(html).toContain('Stale snapshot');
  });

  it('asserts no leftover mock/stub strings appear in the rendered output', () => {
    const html = render(
      createElement(DailySnapshotPanel, { fetchResult: result, now: FIXED_NOW }),
    );
    // If anyone accidentally hardcodes these in the panel, fail loud.
    expect(html.toLowerCase()).not.toContain('lorem ipsum');
    expect(html.toLowerCase()).not.toContain('todo');
    expect(html.toLowerCase()).not.toContain('placeholder');
  });
});

describe('DailySnapshotPanel — empty / error states', () => {
  it('shows the empty banner with the no_recent_row reason', () => {
    const html = render(
      createElement(DailySnapshotPanel, {
        fetchResult: { kind: 'empty', reason: 'no_recent_row' },
        now: FIXED_NOW,
      }),
    );
    expect(html).toContain('snapshot-empty');
    expect(html).toContain('No snapshot');
  });

  it('shows the empty banner with the unconfigured reason', () => {
    const html = render(
      createElement(DailySnapshotPanel, {
        fetchResult: { kind: 'empty', reason: 'unconfigured' },
        now: FIXED_NOW,
      }),
    );
    expect(html).toContain('snapshot-empty');
    expect(html).toContain('NEXT_PUBLIC_SUPABASE_URL');
  });

  it('shows the error banner with the message', () => {
    const html = render(
      createElement(DailySnapshotPanel, {
        fetchResult: { kind: 'error', message: 'connection refused' },
        now: FIXED_NOW,
      }),
    );
    expect(html).toContain('snapshot-error');
    expect(html).toContain('connection refused');
    expect(html).toContain('Retry');
  });
});
