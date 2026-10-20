import { describe, expect, it, vi, afterEach } from 'vitest';
import {
  barsResponseToVelaBars,
  fetchVelaBars,
  normalizeVelaSymbol,
  normalizeVelaTimeframe,
  toVelaSpikeBar,
  VelaBarsError,
  VELA_DEFAULT_SYMBOL,
  VELA_DEFAULT_TIMEFRAME,
} from './vela-bars';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('normalizeVelaSymbol', () => {
  it('falls back to the crypto default on blank input', () => {
    expect(normalizeVelaSymbol(null)).toBe(VELA_DEFAULT_SYMBOL);
    expect(normalizeVelaSymbol('   ')).toBe(VELA_DEFAULT_SYMBOL);
  });

  it('trims but otherwise passes the listing through', () => {
    expect(normalizeVelaSymbol('  aapl ')).toBe('aapl');
  });
});

describe('normalizeVelaTimeframe', () => {
  it('accepts the endpoint vocabulary case-insensitively', () => {
    expect(normalizeVelaTimeframe('1D')).toBe('1d');
    expect(normalizeVelaTimeframe('1wk')).toBe('1wk');
  });

  it('falls back to the default on unknown input', () => {
    expect(normalizeVelaTimeframe('D')).toBe(VELA_DEFAULT_TIMEFRAME);
    expect(normalizeVelaTimeframe(null)).toBe(VELA_DEFAULT_TIMEFRAME);
  });
});

describe('toVelaSpikeBar', () => {
  it('maps an ISO timestamp to epoch ms and keeps volume', () => {
    expect(
      toVelaSpikeBar({
        timestamp: '2024-10-01',
        open: 100,
        high: 104,
        low: 99,
        close: 103,
        volume: 1200,
      })
    ).toEqual({ t: Date.parse('2024-10-01'), o: 100, h: 104, l: 99, c: 103, v: 1200 });
  });

  it('omits volume when absent and accepts null volume', () => {
    expect(
      toVelaSpikeBar({ timestamp: '2024-10-01', open: 1, high: 2, low: 0.5, close: 1.5 })
    ).toEqual({ t: Date.parse('2024-10-01'), o: 1, h: 2, l: 0.5, c: 1.5 });
    expect(
      toVelaSpikeBar({
        timestamp: '2024-10-01',
        open: 1,
        high: 2,
        low: 0.5,
        close: 1.5,
        volume: null,
      })
    ).toEqual({ t: Date.parse('2024-10-01'), o: 1, h: 2, l: 0.5, c: 1.5 });
  });

  it('drops bars Vela cannot draw', () => {
    // Unparseable timestamp.
    expect(
      toVelaSpikeBar({ timestamp: 'not-a-date', open: 1, high: 2, low: 0.5, close: 1.5 })
    ).toBeNull();
    // Nullable o/h/l from the endpoint (BarsBar.open/high/low are optional).
    expect(
      toVelaSpikeBar({
        timestamp: '2024-10-01',
        open: null,
        high: 2,
        low: 0.5,
        close: 1.5,
      })
    ).toBeNull();
    expect(toVelaSpikeBar(null)).toBeNull();
  });
});

describe('barsResponseToVelaBars', () => {
  it('maps newest-last payload bars and drops incomplete rows', () => {
    expect(
      barsResponseToVelaBars({
        bars: [
          { timestamp: '2024-10-01', open: 100, high: 104, low: 99, close: 103, volume: 5 },
          { timestamp: '2024-10-02', open: null, high: 2, low: 1, close: 1.5 },
        ],
      })
    ).toEqual([{ t: Date.parse('2024-10-01'), o: 100, h: 104, l: 99, c: 103, v: 5 }]);
  });

  it('returns [] for non-payloads', () => {
    expect(barsResponseToVelaBars(null)).toEqual([]);
    expect(barsResponseToVelaBars({})).toEqual([]);
  });
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('fetchVelaBars', () => {
  it('GETs keyless /bars with symbol + timeframe and maps the payload', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        symbol: 'BTC-USD',
        timeframe: '1d',
        limit: 120,
        count: 1,
        bars: [
          { timestamp: '2024-10-01', open: 100, high: 104, low: 99, close: 103, volume: 5 },
        ],
        source: 'gloomberb',
        stale: false,
        delay_note: 'Free-tier data delayed up to 15 minutes',
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchVelaBars('BTC-USD', '1d', { baseUrl: 'http://127.0.0.1:8001' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit?];
    expect(url).toBe('http://127.0.0.1:8001/bars?symbol=BTC-USD&timeframe=1d');
    // Keyless: no Authorization header on the read.
    expect(init?.headers).toBeUndefined();
    expect(result.bars).toEqual([
      { t: Date.parse('2024-10-01'), o: 100, h: 104, l: 99, c: 103, v: 5 },
    ]);
    expect(result.delayNote).toBe('Free-tier data delayed up to 15 minutes');
  });

  it('throws a typed error carrying the HTTP status on failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'bad tf' }, 422)));
    const err = await fetchVelaBars('BTC-USD', 'nope').catch((e) => e);
    expect(err).toBeInstanceOf(VelaBarsError);
    expect((err as VelaBarsError).status).toBe(422);
    expect((err as Error).message).toBe('bad tf');
  });

  it('reads the digiquant error envelope message when detail is absent', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ error: { code: 'http_422', message: "timeframe must be one of 1m (got '3D')" } }, 422)
      )
    );
    const err = await fetchVelaBars('BTC-USD', '3D').catch((e) => e);
    expect((err as VelaBarsError).status).toBe(422);
    expect((err as Error).message).toBe("timeframe must be one of 1m (got '3D')");
  });

  it('throws a status-less typed error on transport failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new Error('boom'))));
    const err = await fetchVelaBars('BTC-USD', '1d').catch((e) => e);
    expect(err).toBeInstanceOf(VelaBarsError);
    expect((err as VelaBarsError).status).toBeNull();
  });
});
