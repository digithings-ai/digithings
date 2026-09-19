import { describe, expect, it } from 'vitest';
import {
  countDeltaTouchesForDoc,
  countResearchChangelogTouchesForDoc,
  docAffectedByDeltaPaths,
  docMatchesLibraryScope,
  getDocLibraryTier,
  isEvolutionSourcesEmpty,
  isPortfolioRecommendationPath,
} from './library-doc-tier';
import type { Doc, ResearchChangelogMeta } from './types';

function doc(partial: Partial<Pick<Doc, 'path' | 'segment' | 'type'>>): Pick<
  Doc,
  'path' | 'segment' | 'type'
> {
  return {
    path: '',
    segment: null,
    type: null,
    ...partial,
  };
}

describe('getDocLibraryTier (#3398 thesis + screener routing)', () => {
  it('routes evolution paths to evolution', () => {
    expect(getDocLibraryTier(doc({ path: 'evolution/beliefs.md' }))).toBe('evolution');
  });

  it('routes thesis/ and bare opportunity-screener into portfolio (WP-B publish keys)', () => {
    expect(getDocLibraryTier(doc({ path: 'thesis/thesis-review' }))).toBe('portfolio');
    expect(getDocLibraryTier(doc({ path: 'opportunity-screener' }))).toBe('portfolio');
    expect(getDocLibraryTier(doc({ path: 'opportunity-screener.json' }))).toBe('portfolio');
  });

  it('keeps Track B PM prefixes in portfolio', () => {
    expect(getDocLibraryTier(doc({ path: 'market-thesis-exploration/btc' }))).toBe('portfolio');
    expect(getDocLibraryTier(doc({ path: 'thesis-vehicle-map/map' }))).toBe('portfolio');
    expect(getDocLibraryTier(doc({ path: 'opportunity-screen/roster' }))).toBe('portfolio');
    expect(getDocLibraryTier(doc({ path: 'pm-allocation-memo/memo' }))).toBe('portfolio');
    expect(getDocLibraryTier(doc({ path: 'deliberation-transcript/run-1' }))).toBe('portfolio');
    expect(getDocLibraryTier(doc({ path: 'asset-recommendations/iau' }))).toBe('portfolio');
  });

  it('classifies portfolio by basename, segment, or type when path is flat', () => {
    expect(getDocLibraryTier(doc({ path: 'runs/today/deliberation.md' }))).toBe('portfolio');
    expect(getDocLibraryTier(doc({ path: 'misc/note', segment: 'rebalance-decision' }))).toBe(
      'portfolio',
    );
    expect(getDocLibraryTier(doc({ path: 'misc/note', type: 'deliberation-memo' }))).toBe(
      'portfolio',
    );
  });

  it('defaults remaining research memos to research', () => {
    expect(getDocLibraryTier(doc({ path: 'deltas/macro.delta.md' }))).toBe('research');
    expect(getDocLibraryTier(doc({ path: 'digest' }))).toBe('research');
    expect(getDocLibraryTier(doc({ path: 'inputs' }))).toBe('research');
    expect(getDocLibraryTier(doc({ path: 'bias-row' }))).toBe('research');
  });
});

describe('docMatchesLibraryScope', () => {
  it('scope=all always matches', () => {
    expect(docMatchesLibraryScope(doc({ path: 'anything' }), 'all')).toBe(true);
  });

  it('research hides machine delta artifacts but keeps per-segment deltas/*', () => {
    expect(docMatchesLibraryScope(doc({ path: 'delta-request.json' }), 'research')).toBe(false);
    expect(docMatchesLibraryScope(doc({ path: 'document-deltas/foo' }), 'research')).toBe(false);
    expect(docMatchesLibraryScope(doc({ path: 'deltas/macro.delta.md' }), 'research')).toBe(true);
    expect(docMatchesLibraryScope(doc({ path: 'deltas/sectors/technology.delta.md' }), 'research')).toBe(
      true,
    );
  });

  it('portfolio and evolution scopes filter by tier only', () => {
    expect(docMatchesLibraryScope(doc({ path: 'thesis/thesis-review' }), 'portfolio')).toBe(true);
    expect(docMatchesLibraryScope(doc({ path: 'deltas/macro.delta.md' }), 'portfolio')).toBe(false);
    expect(docMatchesLibraryScope(doc({ path: 'evolution/beliefs.md' }), 'evolution')).toBe(true);
    expect(docMatchesLibraryScope(doc({ path: 'digest' }), 'evolution')).toBe(false);
  });

  it('research excludes portfolio-tier docs', () => {
    expect(docMatchesLibraryScope(doc({ path: 'opportunity-screener' }), 'research')).toBe(false);
    expect(docMatchesLibraryScope(doc({ path: 'thesis/thesis-review' }), 'research')).toBe(false);
  });
});

describe('isPortfolioRecommendationPath', () => {
  it('detects legacy portfolio-recommendation paths case-insensitively', () => {
    expect(isPortfolioRecommendationPath('portfolio-recommendation.json')).toBe(true);
    expect(isPortfolioRecommendationPath('Archive/Portfolio-Recommendation/v1')).toBe(true);
    expect(isPortfolioRecommendationPath('opportunity-screener')).toBe(false);
  });
});

describe('isEvolutionSourcesEmpty', () => {
  it('treats non-objects and wrong doc_type as empty / not-empty correctly', () => {
    expect(isEvolutionSourcesEmpty(null)).toBe(true);
    expect(isEvolutionSourcesEmpty([])).toBe(true);
    expect(isEvolutionSourcesEmpty({ doc_type: 'beliefs', body: {} })).toBe(false);
  });

  it('requires notes or source_ratings for evolution_sources', () => {
    expect(
      isEvolutionSourcesEmpty({
        doc_type: 'evolution_sources',
        body: { notes: '', source_ratings: [] },
      }),
    ).toBe(true);
    expect(
      isEvolutionSourcesEmpty({
        doc_type: 'evolution_sources',
        body: { notes: 'keep duration short', source_ratings: [] },
      }),
    ).toBe(false);
    expect(
      isEvolutionSourcesEmpty({
        doc_type: 'evolution_sources',
        body: { notes: '', source_ratings: [{ source: 'fed' }] },
      }),
    ).toBe(false);
  });
});

describe('docAffectedByDeltaPaths / countDeltaTouchesForDoc', () => {
  it('maps digest to regime/market/actionable/risks/segments/portfolio/digest roots', () => {
    expect(docAffectedByDeltaPaths('digest', ['/regime/bias'])).toBe(true);
    expect(docAffectedByDeltaPaths('digest', ['/market_data/spy'])).toBe(true);
    expect(docAffectedByDeltaPaths('digest', ['/unrelated'])).toBe(false);
    expect(docAffectedByDeltaPaths('digest', [])).toBe(false);
  });

  it('matches stem with hyphen/underscore variants', () => {
    expect(docAffectedByDeltaPaths('us-equities.json', ['/us_equities/note'])).toBe(true);
    expect(docAffectedByDeltaPaths('us-equities.json', ['/us-equities/note'])).toBe(true);
    expect(docAffectedByDeltaPaths('us-equities.json', ['/usequities'])).toBe(true);
    expect(docAffectedByDeltaPaths('macro.json', ['/bonds/duration'])).toBe(false);
    expect(docAffectedByDeltaPaths('delta-request.json', ['/anything'])).toBe(false);
  });

  it('counts unique changed ∪ op paths that touch the doc', () => {
    expect(
      countDeltaTouchesForDoc(
        'digest',
        ['/regime/a', '/regime/a', '/unrelated'],
        ['/market_data/b'],
      ),
    ).toBe(2);
  });
});

describe('countResearchChangelogTouchesForDoc', () => {
  it('returns 0 for missing meta and matches path suffixes', () => {
    expect(countResearchChangelogTouchesForDoc('deltas/macro.delta.md', null)).toBe(0);
    const meta: ResearchChangelogMeta = {
      baseline_date: '2026-08-31',
      items: [
        { target_document_key: 'deltas/macro.delta.md', status: 'edited' },
        { target_document_key: 'macro.delta.md', status: 'edited' },
        { target_document_key: 'other.md', status: 'edited' },
      ],
    };
    // Exact + suffix match on the same doc path → two touches
    expect(countResearchChangelogTouchesForDoc('deltas/macro.delta.md', meta)).toBe(2);
  });
});
