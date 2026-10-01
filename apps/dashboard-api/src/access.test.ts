import { describe, expect, it } from "vitest";
import { buildManifest, grantedRoutes, parseCaller, DESKS } from "./access";

const h = (o: Record<string, string>) => ({ get: (k: string) => o[k] ?? null });
const desk = (m: ReturnType<typeof buildManifest>, id: string) => m.desks.find((d) => d.id === id)!;
const page = (m: ReturnType<typeof buildManifest>, d: string, p: string) => desk(m, d).pages.find((x) => x.path === p)!;

describe("parseCaller", () => {
  it("fails closed to free with no groups", () => {
    expect(parseCaller(h({}))).toEqual({ tier: "free", groups: [] });
    expect(parseCaller(h({ "x-digi-tier": "root" }))).toEqual({ tier: "free", groups: [] });
  });
  it("reads tier and groups, case-insensitively", () => {
    expect(parseCaller(h({ "x-digi-tier": "PRO", "x-digi-groups": "12X, beta" }))).toEqual({ tier: "pro", groups: ["12x", "beta"] });
  });
});

describe("buildManifest", () => {
  it("free: baseline open, pro pages and blocks locked with a reason", () => {
    const m = buildManifest({ tier: "free", groups: [] });
    expect(desk(m, "baseline").access).toBe("granted");
    expect(page(m, "baseline", "/brief").access).toBe("granted");
    expect(page(m, "baseline", "/portfolio/ledger")).toMatchObject({ access: "locked", reason: "Requires pro" });
    const live = page(m, "baseline", "/brief").blocks.find((k) => k.id === "live")!;
    expect(live).toMatchObject({ access: "locked", reason: "Requires pro" });
  });
  it("fx desk is locked to non-members, and everything beneath it", () => {
    const m = buildManifest({ tier: "max", groups: [] });
    expect(desk(m, "fx")).toMatchObject({ access: "locked", reason: "Requires the 12x group" });
    expect(desk(m, "fx").pages.every((p) => p.access === "locked" && p.blocks.every((k) => k.access === "locked"))).toBe(true);
  });
  it("12x member on free tier gets the fx desk", () => {
    const m = buildManifest({ tier: "free", groups: ["12x"] });
    expect(desk(m, "fx").access).toBe("granted");
    expect(page(m, "fx", "/fx/ideas").access).toBe("granted");
  });
  it("pro unlocks baseline pro pages but not max-only deploy", () => {
    const m = buildManifest({ tier: "pro", groups: [] });
    expect(page(m, "baseline", "/portfolio/ledger").access).toBe("granted");
    expect(page(m, "baseline", "/strategies/deploy").access).toBe("locked");
  });
  it("omits hidden-gated nodes the caller fails", () => {
    const desks = [{ id: "x", label: "X", blurb: "", pages: [{ path: "/x", label: "X", tier: "max" as const, hidden: true, blocks: [] }] }];
    expect(buildManifest({ tier: "free", groups: [] }, desks).desks[0]!.pages).toEqual([]);
  });
  it("grantedRoutes lists only callable routes, without query strings", () => {
    const free = grantedRoutes(buildManifest({ tier: "free", groups: [] }));
    expect(free).toContain("/brief");
    expect(free).not.toContain("/kpis/live");
    expect(free).not.toContain("/fx/ideas");
    expect(free.every((r) => !r.includes("?"))).toBe(true);
  });
  it("page paths are unique per desk", () => {
    for (const d of DESKS) expect(new Set(d.pages.map((p) => p.path)).size).toBe(d.pages.length);
  });
});
