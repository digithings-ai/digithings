import { describe, expect, it } from 'vitest';
import {
  DESK_PATH_ALIASES,
  DESK_PATHS,
  DIGICON_ENDPOINTS,
  resolveDeskPath,
  tableEndpoint,
} from './paths';

describe('resolveDeskPath', () => {
  it('maps brief, portfolio, allocations, ledger, and performance onto the real routes', () => {
    expect(resolveDeskPath('/house/brief')).toMatchObject({
      endpoint: DIGICON_ENDPOINTS.brief,
      client: 'getBrief',
    });
    expect(resolveDeskPath('/house/brief/book')).toMatchObject({
      endpoint: DIGICON_ENDPOINTS.portfolio,
      client: 'getPortfolio',
    });
    expect(resolveDeskPath('/house/portfolio/holdings')).toMatchObject({
      endpoint: DIGICON_ENDPOINTS.allocations,
      client: 'getAllocations',
    });
    expect(resolveDeskPath('/house/portfolio/ledger')).toMatchObject({
      endpoint: DIGICON_ENDPOINTS.ledger,
      client: 'getLedger',
    });
    expect(resolveDeskPath('/house/portfolio/tearsheet')).toMatchObject({
      endpoint: DIGICON_ENDPOINTS.performance,
      client: 'getPerformance',
      also: [DIGICON_ENDPOINTS.navSeries],
    });
  });

  it('treats /book and /movers as chrome aliases, not new routes', () => {
    expect(DESK_PATH_ALIASES['/book']).toBe('/house/brief/book');
    expect(DESK_PATH_ALIASES['/movers']).toBe('/house/brief/movers');
    expect(resolveDeskPath('/book')?.endpoint).toBe('/portfolio');
    const movers = resolveDeskPath('/movers');
    expect(movers?.client).toBe('deriveMovers');
    expect(movers?.endpoint).toBeNull();
    expect(movers?.also).toEqual(['/allocations', '/v1/market/closes']);
    expect(DESK_PATHS.some((entry) => entry.endpoint === '/movers' || entry.endpoint === '/book')).toBe(
      false,
    );
  });

  it('points table panes at GET /v1/tables/:table and leaves missing panes without a route', () => {
    expect(resolveDeskPath('/house/brief/signals')?.endpoint).toBe(tableEndpoint('theses'));
    expect(resolveDeskPath('/house/pipeline')?.tables).toEqual([
      'run_health',
      'documents',
      'run_event_trace',
    ]);
    expect(resolveDeskPath('/house/brief/gloomberg')).toMatchObject({
      endpoint: null,
      mode: 'missing',
    });
    expect(resolveDeskPath('/house/strategies')?.mode).toBe('missing');
    expect(resolveDeskPath('/rates-watch/digest')?.endpoint).toBeNull();
  });

  it('resolves a holdings ticker suffix onto the symbol pane', () => {
    expect(resolveDeskPath('/house/portfolio/holdings/DBO')).toMatchObject({
      chromePath: '/house/portfolio/holdings/:ticker',
      endpoint: '/allocations',
    });
  });
});
