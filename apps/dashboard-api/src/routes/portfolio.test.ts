import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";

const ENV: Env = {
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
};
const FREE: Env = { SUPABASE_URL: "https://core.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "core-key" };

function mockFetch(handler: (url: string) => unknown): void {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => Response.json(handler(String(url)))));
}

afterEach(() => vi.unstubAllGlobals());

async function body(path: string, env: Env = ENV): Promise<Record<string, unknown>> {
  const res = await app.fetch(new Request(`https://x${path}`), env);
  return { status: res.status, ...(await res.json() as object) };
}

describe("phase 1 portfolio routes", () => {
  it("free caller is forbidden on brief routes; brief is not", async () => {
    mockFetch(() => []);
    expect((await app.fetch(new Request("https://x/attribution"), FREE)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/theses/signals"), FREE)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/ledger/cash"), FREE)).status).toBe(403);
    expect((await app.fetch(new Request("https://x/performance/drawdown"), FREE)).status).toBe(403);
    const brief = await app.fetch(new Request("https://x/attribution", { headers: { "x-digi-tier": "brief" } }), FREE);
    expect(brief.status).toBe(200);
  });

  it("theses envelope joins vehicles and does not invent evidence", async () => {
    mockFetch((url) => {
      if (url.includes("/theses?")) return [{ id: "t1", name: "Gold", state: "active", date: "2026-09-28" }];
      if (url.includes("/thesis_vehicles")) return [{ thesis_id: "t1", ticker: "GLD", date: "2026-09-28" }];
      return [];
    });
    const res = await body("/theses");
    expect(res.status).toBe(200);
    const data = res.data as { theses: { id: string; vehicles: string[]; evidence: null }[]; counts: { active: number } };
    expect(data.theses[0]).toMatchObject({ id: "t1", vehicles: ["GLD"], evidence: null });
    expect(data.counts.active).toBe(1);
    expect(res.provenance).toMatchObject({ source: "core:theses" });
    // The fixture's `date` is load-bearing: this pane ages off it, so a pane that
    // aged by anything else would not report the row's own business date.
    expect(res.as_of).toBe("2026-09-28");
  });

  // The test above uses `id: "t1"`, which coincides with `thesis_id` and so
  // cannot tell a working join from a dead one. Live core rows carry a uuid in
  // `id` and the text business key in `thesis_id`, and the vehicles lookup must
  // key on the latter: joined on `id`, it matched 0 of 3256 live rows.
  it("theses vehicles join on thesis_id, not the uuid id", async () => {
    mockFetch((url) => {
      if (url.includes("/theses?")) return [
        { id: "fd49f84b-114b-4e73-ab87-f16939664f97", thesis_id: "gold-bid", name: "Gold", status: "ACTIVE", date: "2026-09-28" },
      ];
      if (url.includes("/thesis_vehicles")) return [{ thesis_id: "gold-bid", ticker: "GLD", date: "2026-09-28" }];
      return [];
    });
    const res = await body("/theses");
    expect(res.status).toBe(200);
    const data = res.data as { theses: { id: string; vehicles: string[] }[] };
    expect(data.theses[0].id).toBe("fd49f84b-114b-4e73-ab87-f16939664f97");
    expect(data.theses[0].vehicles).toEqual(["GLD"]);
  });

  it("signals keeps only needs_resolution rows", async () => {
    mockFetch((url) => (url.includes("/theses?") ? [{ id: "a", needs_resolution: true, name: "A", date: "2026-09-28" }, { id: "b", needs_resolution: false, name: "B", date: "2026-09-28" }] : []));
    const res = await body("/theses/signals", { ...ENV, DASHBOARD_DEV_CALLER: "brief" });
    const data = res.data as { theses: { id: string }[] };
    expect(data.theses.map((t) => t.id)).toEqual(["a"]);
  });

  // DIG-401: `theses` keeps one row per thesis per business `date`, so an
  // unfiltered read repeats every thesis across dates and inflates every count.
  // Only the newest date is the current book.
  it("theses ages by date and keeps only the newest date", async () => {
    mockFetch((url) => {
      if (url.includes("/thesis_vehicles")) return [
        { thesis_id: "t1", ticker: "GLD", date: "2026-09-28" },
        { thesis_id: "t1", ticker: "IAU", date: "2026-09-27" },
        { thesis_id: "t2", ticker: "EUR/USD", date: "2026-09-28" },
      ];
      if (url.includes("/theses?")) return [
        { id: "uuid-t1", thesis_id: "t1", name: "Gold", status: "ACTIVE", date: "2026-09-28" },
        { id: "uuid-t1-old", thesis_id: "t1", name: "Gold", status: "ACTIVE", date: "2026-09-27" },
        { id: "uuid-t2", thesis_id: "t2", name: "Front-end easing", status: "CHALLENGED", date: "2026-09-28" },
        { id: "uuid-t3", thesis_id: "t3", name: "Stale only", status: "ACTIVE", date: "2026-09-20" },
      ];
      return [];
    });
    const res = await body("/theses");
    const payload = res as { status: number; data: { theses: { id: string; vehicles: string[] }[]; counts: { active: number } }; as_of: string | null; provenance: { source: string; tip_date: string | null } };
    expect(payload.status).toBe(200);
    // `date` is the run; provenance names the core table it came from.
    expect(payload.as_of).toBe("2026-09-28");
    expect(payload.provenance.tip_date).toBe("2026-09-28");
    expect(payload.provenance.source).toBe("core:theses");
    // One row per thesis per date: t1's older row and the tip-stale t3 are out.
    expect(payload.data.theses.map((t) => t.id)).toEqual(["uuid-t1", "uuid-t2"]);
    // Vehicles are dated too — holding them at every date would show each thesis
    // every ticker it has ever carried.
    expect(payload.data.theses[0].vehicles).toEqual(["GLD"]);
    expect(payload.data.theses[1].vehicles).toEqual(["EUR/USD"]);
    expect(payload.data.counts.active).toBe(1);
  });

  // `updated_at` is a row write timestamp, not a run. A pane that ages by it
  // looks current after a no-op edit, so it may never be the as_of even though
  // core `theses` carries the column.
  it("theses does not age by updated_at", async () => {
    mockFetch((url) => (url.includes("/theses?")
      ? [{ id: "t1", thesis_id: "t1", name: "Gold", status: "ACTIVE", date: "2026-09-28", updated_at: "2026-10-03T04:05:06Z" }]
      : []));
    const res = await body("/theses");
    expect(res.status).toBe(200);
    expect(res.as_of).toBe("2026-09-28");
  });

  // Rows carrying no business `date` yield no book: `maxThesisDate` is null and
  // `rowsAtDate` treats null as "nothing to keep", so the pane must report an
  // empty book with a null as_of rather than falling back to a write timestamp.
  it("theses without a dated row returns an empty book and a null as_of", async () => {
    mockFetch((url) => (url.includes("/theses?")
      ? [{ id: "t1", thesis_id: "t1", name: "Gold", status: "ACTIVE", updated_at: "2026-10-03T04:05:06Z" }]
      : []));
    const res = await body("/theses");
    const payload = res as { status: number; data: { theses: unknown[]; counts: { active: number } }; as_of: string | null };
    expect(payload.status).toBe(200);
    expect(payload.as_of).toBeNull();
    expect(payload.data.theses).toEqual([]);
    expect(payload.data.counts.active).toBe(0);
  });

  // DIG-486: the exact wire shape for a fixed three-thesis book. The old mapper
  // read `evidence`, `kill_condition` and `note` — none of which are columns on
  // core `theses` — so all three were permanently null, and its `watch`/`exited`
  // buckets matched no token `chk_theses_status` allows, so both were
  // permanently zero. This fixture pins every cell and every count.
  it("theses returns the exact shape for a dated three-thesis book", async () => {
    mockFetch((url) => {
      if (url.includes("thesis_vehicles")) return [
        { date: "2026-09-28", thesis_id: "gold-bid", ticker: "GLD" },
        { date: "2026-09-28", thesis_id: "gold-bid", ticker: "IAU" },
        // SLV is on an older date and must not ride along with today's book.
        { date: "2026-09-27", thesis_id: "gold-bid", ticker: "SLV" },
        { date: "2026-09-28", thesis_id: "vehicle-tesla-margin", ticker: "TSLA" },
      ];
      if (url.includes("/theses?")) return [
        {
          id: "uuid-gold", thesis_id: "gold-bid", name: "Gold bid", status: "ACTIVE", thesis_kind: "market",
          validation_criteria: [{ condition: "real yields below 2%" }, { condition: "DXY under 100" }],
          invalidation_criteria: [{ condition: "real yields above 3%" }],
          invalidation: null, notes: "Trimmed on 2026-09-24.", date: "2026-09-28",
        },
        {
          // No jsonb criteria: the kill condition must still read off the
          // free-text `invalidation` column from migration 001.
          id: "uuid-fe", thesis_id: "front-end-easing", name: "Front-end easing", status: "MONITORING", thesis_kind: "market",
          validation_criteria: null, invalidation_criteria: null,
          invalidation: "Fed re-tightens before March", notes: null, date: "2026-09-28",
        },
        {
          id: "uuid-tsla", thesis_id: "vehicle-tesla-margin", name: "Tesla margin", status: "INVALIDATED", thesis_kind: "vehicle",
          validation_criteria: [], invalidation_criteria: [], invalidation: null,
          notes: "Killed: the pricing action reversed.", date: "2026-09-28",
        },
      ];
      return [];
    });
    const res = await body("/theses");
    expect(res.status).toBe(200);
    expect(res.data).toEqual({
      theses: [
        {
          id: "uuid-gold", name: "Gold bid", state: "active", vehicles: ["GLD", "IAU"],
          evidence: "real yields below 2%; DXY under 100",
          kill_condition: "real yields above 3%",
          note: "Trimmed on 2026-09-24.",
        },
        {
          id: "uuid-fe", name: "Front-end easing", state: "monitoring", vehicles: [],
          evidence: null, kill_condition: "Fed re-tightens before March", note: null,
        },
        {
          id: "uuid-tsla", name: "Tesla margin", state: "invalidated", vehicles: ["TSLA"],
          evidence: null, kill_condition: null, note: "Killed: the pricing action reversed.",
        },
      ],
      counts: {
        // MONITORING is a live thesis under management, so it is `watch`;
        // INVALIDATED is off the book, so it is `exited`.
        active: 1, watch: 1, exited: 1,
        by_status: {
          active: 1, monitoring: 1, challenged: 0, closed: 0,
          invalidated: 1, paused: 0, new: 0, unknown: 0,
        },
      },
    });
    expect(res.as_of).toBe("2026-09-28");
  });

  // `watch` and `exited` are rollups over tokens the constraint allows, so a
  // row whose status the constraint would reject must land in `unknown` and
  // inflate neither — `WATCH` in the table is not the `watch` bucket. The row
  // still shows its own status: the pane reports the book, it does not relabel.
  it("theses buckets a status the constraint would reject as unknown", async () => {
    mockFetch((url) => (url.includes("/theses?")
      ? [
        { id: "uuid-a", thesis_id: "a", name: "A", status: null, date: "2026-09-28" },
        { id: "uuid-b", thesis_id: "b", name: "B", status: "WATCH", date: "2026-09-28" },
      ]
      : []));
    const res = await body("/theses");
    const payload = res as { data: { theses: { state: string }[]; counts: { active: number; watch: number; exited: number; by_status: { unknown: number } } } };
    expect(payload.data.theses.map((t) => t.state)).toEqual(["—", "watch"]);
    expect(payload.data.counts.active).toBe(0);
    expect(payload.data.counts.watch).toBe(0);
    expect(payload.data.counts.exited).toBe(0);
    expect(payload.data.counts.by_status.unknown).toBe(2);
  });

  it("drawdown is computed from NAV and stays null without a second point", async () => {
    mockFetch(() => [{ date: "2026-01-01", nav: 100 }, { date: "2026-01-03", nav: 80 }]);
    const res = await body("/performance/drawdown", { ...ENV, DASHBOARD_DEV_CALLER: "brief" });
    const data = res.data as { max_pct: number; current_pct: number; series: unknown[]; episodes: unknown[] };
    expect(data.max_pct).toBeCloseTo(-20);
    expect(data.current_pct).toBeCloseTo(-20);
    expect(data.series).toHaveLength(2);
    expect(data.episodes).toEqual([]);
  });

  it("enriched book joins a name and leaves an unknown sleeve null", async () => {
    mockFetch((url) => {
      if (url.includes("/positions?")) return [{ date: "2026-08-01", ticker: "GLD", weight_pct: 10, current_price: 2, shares: 3 }];
      if (url.includes("/instruments")) return [{ ticker: "GLD", name: "Gold", instrument_type: "nope" }];
      return [];
    });
    const res = await body("/allocations/enriched");
    const data = res.data as { rows: { name: string; sleeve: null; value: number }[]; book_value: number };
    expect(data.rows[0]).toMatchObject({ name: "Gold", sleeve: null, value: 6 });
    expect(data.book_value).toBe(6);
  });

  it("dossier rejects a bad ticker and does not fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await app.fetch(new Request("https://x/dossier/.."), ENV);
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  // `theses` is one row per thesis per date, so a dossier that reads it without an
  // order and `.find()`s the first match resolves whichever date PostgREST happens
  // to return first. The stale row here leads the fixture AND carries `ticker: "GLD"`
  // so the resolver's ticker arm would match it — that isolates the date defect from
  // the join defect, which the next test covers on its own. Note no live `theses` row
  // carries a `ticker` column (the ticker-ish column is `vehicle`); the field is here
  // only to let this fixture rule the join out.
  it("dossier resolves the thesis from the newest date, not an arbitrary one", async () => {
    mockFetch((url) => {
      if (url.includes("/theses?")) {
        return [
          { id: "uuid-gold-stale", date: "2026-09-27", thesis_id: "gold", name: "Gold", status: "EXITED", ticker: "GLD" },
          { id: "uuid-gold", date: "2026-09-28", thesis_id: "gold", name: "Gold bid", status: "ACTIVE" },
        ];
      }
      if (url.includes("/thesis_vehicles")) {
        return [
          { date: "2026-09-28", thesis_id: "gold", ticker: "GLD" },
        ];
      }
      return [];
    });
    const res = await body("/dossier/GLD");
    const data = res.data as { thesis: { id: string; name: string; state: string } | null };
    expect(data.thesis).toEqual({ id: "uuid-gold", name: "Gold bid", state: "ACTIVE" });
  });

  // `vehicleIds` is built from `thesis_id`, so matching it against `str(r.id)`
  // first compares a uuid against a business key and never matches. This fixture
  // omits the `ticker` column so the ticker fallback cannot mask a dead join.
  it("dossier joins thesis_vehicles on thesis_id, not the uuid id", async () => {
    mockFetch((url) => {
      if (url.includes("/theses?")) {
        return [{ id: "uuid-1", date: "2026-09-28", thesis_id: "gold-bid", name: "Gold bid", status: "ACTIVE" }];
      }
      if (url.includes("/thesis_vehicles")) {
        return [{ date: "2026-09-28", thesis_id: "gold-bid", ticker: "GLD" }];
      }
      return [];
    });
    const res = await body("/dossier/GLD");
    const data = res.data as { thesis: { id: string } | null };
    expect(data.thesis?.id).toBe("uuid-1");
  });

  // Vehicles must be narrowed to the same tip date as the thesis book, or the
  // drawer shows mappings the thesis pane no longer holds.
  it("dossier holds vehicles at the newest date too", async () => {
    mockFetch((url) => {
      if (url.includes("/theses?")) {
        return [{ id: "uuid-gold", date: "2026-09-28", thesis_id: "gold-bid", name: "Gold bid", status: "ACTIVE" }];
      }
      if (url.includes("/thesis_vehicles")) {
        return [
          { date: "2026-09-27", thesis_id: "gold-bid-old", ticker: "GLD" },
          { date: "2026-09-28", thesis_id: "gold-bid", ticker: "GLD" },
        ];
      }
      return [];
    });
    const res = await body("/dossier/GLD");
    const data = res.data as { vehicles: string[] };
    expect(data.vehicles).toEqual(["gold-bid"]);
  });

  // Fail-closed: `rowsAtDate` returns [] for a null date, so a `theses` row with no
  // `date` yields no vehicles rather than falling back to `updated_at`. The
  // `thesis === null` assertion here is decoration — pre-fix it is satisfied by the
  // dead uuid join, not by the missing date — so the load-bearing part is the
  // `vehicles` one.
  it("dossier without a dated thesis row withholds the thesis and the vehicles", async () => {
    mockFetch((url) => {
      if (url.includes("/theses?")) {
        return [{ id: "uuid-1", thesis_id: "gold-bid", name: "Gold bid", status: "ACTIVE", updated_at: "2026-09-28T10:00:00Z" }];
      }
      if (url.includes("/thesis_vehicles")) {
        return [{ date: "2026-09-28", thesis_id: "gold-bid", ticker: "GLD" }];
      }
      return [];
    });
    const res = await body("/dossier/GLD");
    const data = res.data as { thesis: unknown; vehicles: string[] };
    expect(res.status).toBe(200);
    expect(data.thesis).toBeNull();
    expect(data.vehicles).toEqual([]);
  });

  // `maxThesisDate` maxima over whatever page PostgREST returned, so `order=date.desc`
  // is the only thing making the tip derivable under `limit`. The other dossier mocks
  // ignore the query string, so without this assertion dropping the order from either
  // read leaves every one of them green.
  it("dossier orders both dated reads so the tip survives the row cap", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      urls.push(String(url));
      return Response.json([]);
    }));
    await app.fetch(new Request("https://x/dossier/GLD"), ENV);
    const theses = urls.find((u) => u.includes("/theses?")) ?? "";
    const vehicles = urls.find((u) => u.includes("/thesis_vehicles")) ?? "";
    expect(theses).toContain("order=date.desc");
    expect(vehicles).toContain("order=date.desc");
  });

  it("unconfigured core fails closed", async () => {
    const res = await app.fetch(new Request("https://x/theses"), { DASHBOARD_DEV_CALLER: "enterprise+12x" });
    expect(res.status).toBe(502);
  });
});
