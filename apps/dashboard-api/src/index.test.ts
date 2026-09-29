/**
 * Scaffold vitest suite: error envelope + GET /healthz + GET /portfolio
 * (book_as_of gate folded in per CONTRACT.md section 0).
 */
import { describe, expect, it } from "vitest";
import app, {
  buildProvenance,
  errorResponse,
  parseCommonParams,
  type Env,
} from "./index";
import { STUB_NULL_AS_OF } from "./stubs";

const NO_ENV: Env = {};

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
  // Slice 0007 decision (a): the route is served by the envelope mount over
  // the stub double (CONTRACT §6.1 documents `invested.definition`), so no
  // Supabase env is needed and the null-book convention is the stub's
  // `asOf=2020-01-01`. The rewire slice swaps the stub for real book reads.
  it("serves the stub book with no secrets configured", async () => {
    const res = await app.fetch(
      new Request("https://x/portfolio?retrieval_pin=pin-9"),
      NO_ENV,
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      retrieval_pin: string;
    };
    expect(body.retrieval_pin).toBe("pin-9");
  });

  it("rejects malformed asOf with bad_request", async () => {
    const res = await app.fetch(new Request("https://x/portfolio?asOf=soon"), NO_ENV);
    expect(res.status).toBe(400);
  });

  it("returns 404 on the stub null-book asOf", async () => {
    const res = await app.fetch(
      new Request(`https://x/portfolio?asOf=${STUB_NULL_AS_OF}`),
      NO_ENV,
    );
    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe("not_found");
  });

  it("serves the committed book with envelope and provenance", async () => {
    const res = await app.fetch(
      new Request("https://x/portfolio?retrieval_pin=pin-3"),
      NO_ENV,
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: {
        book_as_of: string;
        nav_tip: { invested_pct: number; cash_pct: number; contract: string };
        invested: { kpi_pct: number; envelope_pct: number; cash_pct: number; definition: string };
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
    expect(body.data.invested).toEqual({
      kpi_pct: 35.13,
      envelope_pct: 35.13,
      cash_pct: 64.87,
      definition: "accounting_nav_tip",
    });
    expect(body.data.positions.find((p) => p.ticker === "XLV")).toBeDefined();
    expect(Object.keys(body.provenance).sort()).toEqual(
      ["contract", "marks", "seam", "source", "tip_date"].sort(),
    );
  });
});
