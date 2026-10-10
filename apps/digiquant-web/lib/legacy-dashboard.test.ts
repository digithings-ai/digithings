import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { isAccountSurface, publicCatalogPages } from "../components/desk/public-surface";
import { WEB_SLOTS } from "../components/desk/web-slots";
import { deskHref } from "../components/desk/paths";
import {
  DASHBOARD_ACCOUNT_PATHS,
  LEGACY_DESK_PATHS,
  RETIRED_DASHBOARD_PATHS,
  legacyDashboardCloudflareLines,
  legacyDashboardRedirects,
  legacyDashboardTarget,
  legacyDeskHref,
  legacyOlympusCloudflareLines,
} from "./legacy-dashboard.mjs";

describe("legacy dashboard redirects", () => {
  it("covers every desk path and no extra ones", () => {
    const desk = publicCatalogPages().filter((page) => !isAccountSurface(page.path));
    const expected = [...desk.map((page) => page.path), ...WEB_SLOTS.map((slot) => slot.path)];
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

  it("sends retired pages to /app and leaves account pages and other sites alone", () => {
    expect(legacyDashboardTarget("/dashboard/portfolio/performance")).toBe("/app");
    expect(legacyDashboardTarget("/dashboard/twelve-x/")).toBe("/app");
    for (const path of RETIRED_DASHBOARD_PATHS) {
      expect(legacyDashboardTarget(`/dashboard${path}`)).toBe("/app");
    }
    for (const path of DASHBOARD_ACCOUNT_PATHS) {
      expect(legacyDashboardTarget(`/dashboard${path}`)).toBeNull();
      expect(legacyDashboardTarget(`/dashboard${path}/`)).toBeNull();
    }
    expect(legacyDashboardTarget("/app")).toBeNull();
    expect(legacyDashboardTarget("/app/portfolio/")).toBeNull();
    expect(legacyDashboardTarget("/")).toBeNull();
  });

  it("never shadows the account pages apps/dashboard still ships", () => {
    // Supabase Edge Functions pin these (digiquant/supabase/functions/_shared/app-url.ts).
    expect(DASHBOARD_ACCOUNT_PATHS).toEqual(
      expect.arrayContaining(["/login", "/auth/callback", "/settings", "/settings/brokers/callback"]),
    );
    const sources = legacyDashboardRedirects().map((rule) => rule.source);
    expect(sources.some((source) => source.includes(":path") || source.includes("*"))).toBe(false);
    const text = readFileSync(new URL("../public/_redirects", import.meta.url), "utf8");
    expect(text).not.toMatch(/^\/dashboard\/\*/m);
    for (const path of DASHBOARD_ACCOUNT_PATHS) {
      expect(sources).not.toContain(`/dashboard${path}`);
      expect(sources).not.toContain(`/dashboard${path}/`);
      expect(text).not.toMatch(new RegExp(`^/dashboard${path}/? `, "m"));
    }
    for (const path of RETIRED_DASHBOARD_PATHS) {
      expect(LEGACY_DESK_PATHS).not.toContain(path);
      expect(DASHBOARD_ACCOUNT_PATHS).not.toContain(path);
    }
  });

  it("lists longer Next redirects before shorter ones", () => {
    const rules = legacyDashboardRedirects();
    const portfolio = rules.find((rule) => rule.source === "/dashboard/portfolio");
    const holdings = rules.find((rule) => rule.source === "/dashboard/portfolio/holdings");
    const root = rules.find((rule) => rule.source === "/dashboard");
    const slash = rules.find((rule) => rule.source === "/dashboard/");
    const research = rules.find((rule) => rule.source === "/dashboard/research");
    const vela = rules.find((rule) => rule.source === "/dashboard/research/vela-spike");
    expect(portfolio).toEqual({
      source: "/dashboard/portfolio",
      destination: "/app/portfolio/",
      permanent: true,
    });
    expect(holdings?.destination).toBe("/app/portfolio/holdings/");
    expect(root).toEqual({ source: "/dashboard", destination: "/app", permanent: true });
    expect(slash).toEqual({ source: "/dashboard/", destination: "/app", permanent: true });
    expect(rules.at(-1)).toEqual(slash);
    expect(rules.indexOf(holdings!)).toBeLessThan(rules.indexOf(portfolio!));
    expect(rules.indexOf(vela!)).toBeLessThan(rules.indexOf(research!));
  });

  it("publishes the same map in public/_redirects", () => {
    const text = readFileSync(new URL("../public/_redirects", import.meta.url), "utf8");
    const lines = legacyDashboardCloudflareLines();
    expect(lines[0]?.startsWith("/dashboard/portfolio/attribution ")).toBe(true);
    expect(lines.at(-1)).toBe("/dashboard/ /app 308");
    const block = lines.join("\n");
    expect(text).toContain(block);
  });
});

describe("legacy olympus redirects", () => {
  it("sends every /olympus path to its final destination in one hop, never through /dashboard", () => {
    const lines = legacyOlympusCloudflareLines();
    for (const line of lines) {
      const [, destination] = line.split(" ");
      if (destination?.startsWith("/dashboard")) continue; // account paths only
      expect(destination).not.toBe("/dashboard/");
      expect(destination?.startsWith("/dashboard")).toBe(false);
    }
  });

  it("keeps account paths on /dashboard, where apps/dashboard serves them with no further redirect", () => {
    const lines = legacyOlympusCloudflareLines();
    for (const path of DASHBOARD_ACCOUNT_PATHS) {
      expect(lines).toContain(`/olympus${path} /dashboard${path} 308`);
      expect(lines).toContain(`/olympus${path}/ /dashboard${path} 308`);
    }
  });

  it("sends known desk and retired paths straight to /app, matching deskHref", () => {
    const lines = legacyOlympusCloudflareLines();
    for (const path of LEGACY_DESK_PATHS) {
      expect(lines).toContain(`/olympus${path} ${legacyDeskHref(path)} 308`);
    }
    for (const path of RETIRED_DASHBOARD_PATHS) {
      expect(lines).toContain(`/olympus${path} /app/ 308`);
    }
  });

  it("sends the bare root and any unlisted path straight to /app/", () => {
    const lines = legacyOlympusCloudflareLines();
    expect(lines).toContain("/olympus /app/ 308");
    expect(lines).toContain("/olympus/ /app/ 308");
    expect(lines.at(-1)).toBe("/olympus/* /app/ 308");
  });

  it("lists every exact-match rule before the trailing splat", () => {
    const lines = legacyOlympusCloudflareLines();
    const splatIndex = lines.indexOf("/olympus/* /app/ 308");
    expect(splatIndex).toBe(lines.length - 1);
  });

  it("publishes the same map in public/_redirects", () => {
    const text = readFileSync(new URL("../public/_redirects", import.meta.url), "utf8");
    const lines = legacyOlympusCloudflareLines();
    const block = lines.join("\n");
    expect(text).toContain(block);
    expect(text).not.toMatch(/^\/olympus\/\*\s+\/dashboard\/:splat/m);
  });
});
