import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { publicCatalogPages } from "../components/desk/public-surface";
import { WEB_SLOTS } from "../components/desk/web-slots";
import { deskHref } from "../components/desk/paths";
import {
  LEGACY_DESK_PATHS,
  legacyDashboardCloudflareLines,
  legacyDashboardRedirects,
  legacyDashboardTarget,
  legacyDeskHref,
} from "./legacy-dashboard.mjs";

describe("legacy dashboard redirects", () => {
  it("covers every desk path and no extra ones", () => {
    const expected = [...publicCatalogPages().map((page) => page.path), ...WEB_SLOTS.map((slot) => slot.path)];
    expect(new Set(LEGACY_DESK_PATHS)).toEqual(new Set(expected));
    expect(LEGACY_DESK_PATHS).toHaveLength(expected.length);
  });

  it("sends the old root to /app and known paths through deskHref", () => {
    expect(legacyDashboardTarget("/dashboard")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/?tab=brief")).toBe("/app");
    for (const path of LEGACY_DESK_PATHS) {
      expect(legacyDeskHref(path)).toBe(deskHref(path));
      expect(legacyDashboardTarget(`/dashboard${path}`)).toBe(deskHref(path));
      expect(legacyDashboardTarget(`/dashboard${path}/`)).toBe(deskHref(path));
    }
    expect(legacyDashboardTarget("/dashboard/portfolio")).toBe("/app/portfolio/");
    expect(legacyDashboardTarget("/dashboard/portfolio/holdings")).toBe("/app/portfolio/holdings/");
  });

  it("sends unknown old paths to /app and ignores other sites", () => {
    expect(legacyDashboardTarget("/dashboard/login")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/settings/brokers/callback")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/portfolio/performance")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/tools/luxalgo")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/fx")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/fx/ideas")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/twelve-x")).toBe("/app");
    expect(legacyDashboardTarget("/app")).toBeNull();
    expect(legacyDashboardTarget("/app/portfolio/")).toBeNull();
    expect(legacyDashboardTarget("/")).toBeNull();
  });

  it("lists specific Next redirects before the unknown catch-all", () => {
    const rules = legacyDashboardRedirects();
    const portfolio = rules.find((rule) => rule.source === "/dashboard/portfolio");
    const holdings = rules.find((rule) => rule.source === "/dashboard/portfolio/holdings");
    const root = rules.find((rule) => rule.source === "/dashboard");
    const slash = rules.find((rule) => rule.source === "/dashboard/");
    const splat = rules.at(-1);
    expect(portfolio).toEqual({
      source: "/dashboard/portfolio",
      destination: "/app/portfolio/",
      permanent: true,
    });
    expect(holdings?.destination).toBe("/app/portfolio/holdings/");
    expect(root).toEqual({ source: "/dashboard", destination: "/app", permanent: true });
    expect(slash).toEqual({ source: "/dashboard/", destination: "/app", permanent: true });
    expect(splat).toEqual({ source: "/dashboard/:path*", destination: "/app", permanent: true });
    expect(rules.indexOf(holdings!)).toBeLessThan(rules.indexOf(portfolio!));
    expect(rules.indexOf(portfolio!)).toBeLessThan(rules.indexOf(splat!));
  });

  it("publishes the same map in public/_redirects", () => {
    const text = readFileSync(new URL("../public/_redirects", import.meta.url), "utf8");
    const lines = legacyDashboardCloudflareLines();
    expect(lines[0]?.startsWith("/dashboard/portfolio/attribution ")).toBe(true);
    expect(lines.at(-1)).toBe("/dashboard/* /app 308");
    const block = lines.join("\n");
    expect(text).toContain(block);
    expect(text.indexOf("/dashboard/portfolio /app/portfolio/ 308")).toBeLessThan(text.indexOf("/dashboard/* /app 308"));
    expect(text).toContain("/olympus/*              /dashboard/:splat         308");
  });
});
