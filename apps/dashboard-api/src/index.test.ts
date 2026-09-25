/**
 * Scaffold vitest suite: error envelope + GET /healthz + GET /portfolio
 * (book_as_of gate folded in per CONTRACT.md section 0).
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import app, {
  buildPortfolioBody,
  buildProvenance,
  committedBookDate,
  errorResponse,
  parseCommonParams,
  type Env,
} from "./index";

const NO_ENV: Env = {};

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubRest(routes: Record<string, { status: number; body: unknown }>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown) => {
      const url = String(input);
      const path = url.split("/rest/v1/")[1] ?? url;
      for (const [key, value] of Object.entries(routes)) {
        if (path.startsWith(key)) return Response.json(value.body, { status: value.status });
      }
      return Response.json({ message: "no stub" }, { status: 500 });
    }),
  );
}

const BOOK_ENV: Env = {
  SUPABASE_URL: "https://example.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "secret",
};

function bookStubs() {
  stubRest({
    "daily_snapshots": {
      status: 200,
      body: [{ date: "2026-09-24" }],
    },
    "positions?select=date": {
      status: 200,
      body: [{ date: "2026-09-24" }, { date: "2026-09-23" }],
    },
    "public_accounting_nav_history": {
      status: 200,
      body: [
        {
          date: "2026-09-24",
          nav: 99.909,
          invested_pct: 35.13,
          cash_pct: 64.87,
          contract: "legacy_estimate",
        },
      ],
    },
    "positions?select=ticker": {
      status: 200,
      body: [
        { ticker: "XLV", weight_pct: 20.0 },
        { ticker: "CASH", weight_pct: 64.87 },
      ],
    },
  });
}

describe("error envelope", () => {
  it("matches the contract shape with retrieval_pin echo", async () => {
    const res = errorResponse("bad_request", "boom", "pin-1", { asOf: "x" });
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({
      error: { code: "bad_request", message: "boom", details: { asOf: "x" }, retrieval_pin: "pin-1" },
    });
  });

  it("maps codes to statuses", () => {
    expect(errorResponse("not_found", "m", null).status).toBe(404);
    expect(errorResponse("upstream_empty", "m", null).status).toBe(502);
    expect(errorResponse("internal", "m", null).status).toBe(500);
  });
});

describe("provenance builder", () => {
  it("fills contract defaults", () => {
    expect(buildProvenance({ source: "s" })).toEqual({
      source: "s",
      tip_date: null,
      contract: null,
      seam: false,
      marks: "unavailable",
    });
  });
});

describe("common params", () => {
  it("rejects retrieval_pin over 128 chars", () => {
    expect(() =>
      parseCommonParams(new URL(`https://x/portfolio?retrieval_pin=${"p".repeat(129)}`)),
    ).toThrow();
  });

  it("rejects malformed asOf", () => {
    expect(() => parseCommonParams(new URL("https://x/portfolio?asOf=09-24"))).toThrow();
    expect(() => parseCommonParams(new URL("https://x/portfolio?asOf=2026-13-40"))).toThrow();
  });

  it("accepts a valid pair", () => {
    expect(
      parseCommonParams(new URL("https://x/portfolio?asOf=2026-09-24&retrieval_pin=abc")),
    ).toEqual({ asOf: "2026-09-24", retrievalPin: "abc" });
  });
});

describe("GET /healthz", () => {
  it("is auth-exempt liveness", async () => {
    const res = await app.fetch(new Request("https://x/healthz"), NO_ENV);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, service: "dashboard-api" });
  });
});

describe("router", () => {
  it("rejects unknown routes with the envelope", async () => {
    const res = await app.fetch(new Request("https://x/nope"), NO_ENV);
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: { code: string; retrieval_pin: null } };
    expect(body.error.code).toBe("bad_request");
    expect(body.error.retrieval_pin).toBeNull();
  });

  it("has no standalone /book-date route (folded into /portfolio per contract section 0)", async () => {
    const res = await app.fetch(new Request("https://x/book-date"), NO_ENV);
    expect(res.status).toBe(400);
  });
});

describe("GET /portfolio", () => {
  it("fails closed with upstream_empty when secrets are absent", async () => {
    const res = await app.fetch(
      new Request("https://x/portfolio?retrieval_pin=pin-9"),
      NO_ENV,
    );
    expect(res.status).toBe(502);
    const body = (await res.json()) as {
      error: { code: string; retrieval_pin: string };
    };
    expect(body.error.code).toBe("upstream_empty");
    expect(body.error.retrieval_pin).toBe("pin-9");
  });

  it("rejects malformed asOf with bad_request", async () => {
    const res = await app.fetch(new Request("https://x/portfolio?asOf=soon"), BOOK_ENV);
    expect(res.status).toBe(400);
  });

  it("returns 404 when no committed snapshot exists", async () => {
    stubRest({ "daily_snapshots": { status: 200, body: [] } });
    const res = await app.fetch(new Request("https://x/portfolio"), BOOK_ENV);
    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe("not_found");
  });

  it("returns 404 when positions never reach the snapshot (never substitutes latest)", async () => {
    stubRest({
      "daily_snapshots": { status: 200, body: [{ date: "2026-09-24" }] },
      "positions?select=date": { status: 200, body: [{ date: "2026-09-25" }] },
    });
    const res = await app.fetch(new Request("https://x/portfolio"), BOOK_ENV);
    expect(res.status).toBe(404);
  });

  it("returns 502 when the upstream read fails", async () => {
    stubRest({ "daily_snapshots": { status: 200, body: [{ date: "2026-09-24" }] } });
    const res = await app.fetch(
      new Request("https://x/portfolio?retrieval_pin=pin-2"),
      BOOK_ENV,
    );
    expect(res.status).toBe(502);
    const body = (await res.json()) as {
      error: { code: string; retrieval_pin: string };
    };
    expect(body.error.code).toBe("upstream_empty");
    expect(body.error.retrieval_pin).toBe("pin-2");
  });

  it("serves the committed book with envelope and provenance", async () => {
    bookStubs();
    const res = await app.fetch(
      new Request("https://x/portfolio?retrieval_pin=pin-3"),
      BOOK_ENV,
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: {
        book_as_of: string;
        nav_tip: { invested_pct: number; cash_pct: number; contract: string };
        invested: { kpi_pct: number; envelope_pct: number; cash_pct: number };
        positions: Array<{ ticker: string; is_cash: boolean }>;
      };
      as_of: string;
      retrieval_pin: string;
      provenance: Record<string, unknown>;
    };
    expect(body.data.book_as_of).toBe("2026-09-24");
    expect(body.as_of).toBe("2026-09-24");
    expect(body.retrieval_pin).toBe("pin-3");
    expect(body.data.nav_tip.invested_pct).toBe(35.13);
    expect(body.data.invested).toEqual({ kpi_pct: 35.13, envelope_pct: 35.13, cash_pct: 64.87 });
    expect(body.data.positions.find((p) => p.ticker === "CASH")?.is_cash).toBe(true);
    expect(Object.keys(body.provenance).sort()).toEqual(
      ["contract", "marks", "seam", "source", "tip_date"].sort(),
    );
  });
});

describe("committedBookDate", () => {
  it("picks the latest position date on or before the snapshot", () => {
    expect(committedBookDate("2026-09-24", ["2026-09-25", "2026-09-24", "2026-09-23"])).toBe(
      "2026-09-24",
    );
  });

  it("returns null without a snapshot or without a covered date", () => {
    expect(committedBookDate(null, ["2026-09-24"])).toBeNull();
    expect(committedBookDate("2026-09-24", ["2026-09-25"])).toBeNull();
    expect(committedBookDate("2026-09-24", [])).toBeNull();
  });
});

describe("buildPortfolioBody", () => {
  it("falls back to the non-CASH weight sum when the tip has no invested_pct", () => {
    const body = buildPortfolioBody(
      "2026-09-24",
      { date: "2026-09-24", nav: 100, contract: null, invested_pct: null, cash_pct: null },
      [
        { ticker: "XLV", weight_pct: 20, is_cash: false },
        { ticker: "CASH", weight_pct: 80, is_cash: true },
      ],
    ) as { invested: Record<string, number> };
    expect(body.invested).toEqual({ kpi_pct: 20, envelope_pct: 20, cash_pct: 80 });
  });

  it("keeps kpi_pct raw while clamping the envelope at 100", () => {
    const body = buildPortfolioBody(
      "2026-09-24",
      { date: "2026-09-24", nav: 100, contract: null, invested_pct: 150, cash_pct: null },
      [],
    ) as { invested: Record<string, number> };
    expect(body.invested.kpi_pct).toBe(150);
    expect(body.invested.envelope_pct).toBe(100);
  });

  it("fails closed to nulls with no tip and no positions", () => {
    const body = buildPortfolioBody("2026-09-24", null, []) as {
      nav_tip: null;
      invested: Record<string, null>;
    };
    expect(body.nav_tip).toBeNull();
    expect(body.invested).toEqual({ kpi_pct: null, envelope_pct: null, cash_pct: null });
  });
});
