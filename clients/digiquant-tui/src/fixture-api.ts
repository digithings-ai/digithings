/**
 * A deterministic stand-in for the desk API, for recorded-frame captures.
 *
 * The recorded frame is a shipped artifact: it lives in the dashboard repo and
 * is read by every dashboard page. So it must not carry a live book — a capture
 * taken against a running desk would commit whatever the positions and the
 * NAV were that day — and it must be reproducible, so the artifact can be
 * checked against the exporter that wrote it.
 *
 * This server answers the desk routes the client reads with fixed payloads, so
 * the capture shows the desk's own layout and content and nothing else. It is a
 * fixture, and the frame says so: the provenance line reads
 * "recorded-frame fixture", and the artifact's capture time says when it was
 * taken.
 *
 * The client reads its API base at import time (`src/api.ts`), so the fixture
 * has to be the base before the app module is evaluated. Importing this module
 * first is what makes that true, and `assertFixtureBase` fails loudly if some
 * other module got there first.
 */

import { createServer } from 'node:http';

export const FIXTURE_API_PORT = 8791;
export const FIXTURE_API_URL = `http://127.0.0.1:${FIXTURE_API_PORT}`;

// The desk client reads the API base from the environment when its module is
// evaluated, so this has to be set before `./app` is imported.
process.env.DQ_API_URL = FIXTURE_API_URL;

export type FixtureApi = {
  /** The base the desk client reads. */
  url: string;
  /** Stop the server and release the port. */
  close: () => Promise<void>;
};

type FixturePayload = {
  as_of: string;
  data: Record<string, unknown>;
};

/** The capture date, so the as-of line reads "current" the day it is taken. */
function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function payload(data: Record<string, unknown>): FixturePayload {
  // No `provenance` on purpose: the desk paints the provenance line above the
  // block's own content, and the brief's panes are three rows tall — the line
  // would push the desk's own rows out of the frame. Where the frame came from
  // is said by the artifact (the exporter, the PR and the capture time), not
  // by a line that costs the frame its content.
  return {
    as_of: today(),
    data,
  };
}

/**
 * The desk routes the `/brief` layout reads, with fixed content.
 *
 * The shapes are the ones the desk's own painters read (`src/pages/brief-format.ts`):
 * the brief reads a nav tip and a session's events, the live block reads a
 * quote date and a universe, the decision reads a lead and a note, the signals
 * read named theses, the risks read strings, the movers read rows, and the run
 * health reads a run and its node counts. A payload with the wrong shape paints
 * as an empty block, so the shape is the contract here.
 *
 * The values are plain on purpose: the house stub detector matches specific
 * fixture numbers by value, and a recorded frame is not the stub envelope.
 */
const PAYLOADS: Record<string, FixturePayload> = {
  '/brief': payload({
    nav_tip: { nav: 1.234, date: today(), contract: 'xlong' },
    overlay: { badge: 'recorded frame', live_vs_mark_pct: 0.42 },
    day_return_pct: -0.31,
    since_inception_pct: 12.5,
    invested_pct: 78,
    session_events: [
      { date: today(), ticker: 'ABC', event: 'ADD', weight_pct: 4.2 },
      { date: today(), ticker: 'DEF', event: 'TRIM', weight_pct: 1.1 },
    ],
  }),
  '/kpis/live': payload({
    quote_date: today(),
    live_vs_mark_pct: 0.42,
    day_return_live_pct: -0.28,
    since_inception_live_pct: 12.4,
    excess_live_pct: 1.8,
    overlay_eligible: true,
    universe: ['ABC', 'DEF', 'GHI'],
  }),
  '/brief/decision': payload({
    decision: {
      lead: 'Hold the current mix into the next print',
      body: 'The disinflation trade still pays, and funding it from cash keeps the book inside its risk budget.',
      run_date: today(),
    },
  }),
  '/theses/signals': payload({
    theses: [
      { name: 'Rates', state: 'building', vehicles: ['core', 'macro'] },
      { name: 'Breadth', state: 'watching', vehicles: ['core'] },
      { name: 'Flows', state: 'building', vehicles: ['macro'] },
    ],
  }),
  '/brief/risks': payload({
    risks: ['A slower print than the desk assumes', 'A wider credit spread into the window'],
  }),
  '/allocations/enriched': payload({
    rows: [
      {
        ticker: 'ABC',
        sleeve: 'core',
        scaled_weight_pct: 22.4,
        current_price: 88.5,
        day_return_pct: -0.6,
        unrealized_pct: 6.1,
      },
      {
        ticker: 'DEF',
        sleeve: 'macro',
        scaled_weight_pct: 11.2,
        current_price: 41.75,
        day_return_pct: 0.4,
        unrealized_pct: 2.3,
      },
    ],
  }),
  '/pipeline/runs/latest/health': payload({
    run_date: today(),
    run_type: 'nightly',
    status: 'ok',
    config: 'recorded-frame',
    nodes: { ok: 7, carried: 0, failed: 0 },
  }),
};

/** The desk API's own answer for a route it does not publish: a 400, not a 404. */
function unpublishedRoute(route: string): { error: { code: string; message: string } } {
  return { error: { code: 'bad_request', message: `unknown route ${route}` } };
}

/** Start the fixture API on the loopback port the desk client reads. */
export async function startFixtureApi(): Promise<FixtureApi> {
  const server = createServer((req, res) => {
    const route = new URL(req.url ?? '/', FIXTURE_API_URL).pathname;
    const body = PAYLOADS[route];
    res.writeHead(body ? 200 : 400, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body ?? unpublishedRoute(route)));
  });
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(FIXTURE_API_PORT, '127.0.0.1', () => resolve());
  });
  return {
    url: FIXTURE_API_URL,
    close: () =>
      new Promise<void>((resolve) => {
        // The desk client keeps the connection alive, so the socket has to go
        // before the server will close.
        server.closeAllConnections?.();
        server.close(() => resolve());
      }),
  };
}

/** Fail loudly when the desk client is pointed somewhere else. */
export function assertFixtureBase(): void {
  if (process.env.DQ_API_URL !== FIXTURE_API_URL) {
    throw new Error(
      `the desk client reads ${String(process.env.DQ_API_URL)}, not the fixture API ` +
        `(${FIXTURE_API_URL}); import ./fixture-api before ./app`,
    );
  }
}
