import { afterEach, describe, expect, it, vi } from "vitest";
import {
  evaluateFreshness,
  PROBE_USER_AGENT,
  runSiteProbe,
  runStackProbe,
  type ProbeFetch,
} from "./probe";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const NOW = new Date("2026-10-01T00:00:00Z");

function response(status: number, body: string, contentType: string): Response {
  return new Response(body, { status, headers: { "content-type": contentType } });
}

describe("evaluateFreshness", () => {
  it("treats 403 as a warning and 168h-old built_at as STALE", () => {
    expect(
      evaluateFreshness("https://digiquant.io/build-info.json", 403, "", NOW).failed,
    ).toBe(false);
    const body = JSON.stringify({ built_at: "2026-09-01T00:00:00Z" });
    const stale = evaluateFreshness("https://digiquant.io/build-info.json", 200, body, NOW);
    expect(stale.label).toBe("STALE");
    expect(stale.failed).toBe(true);
  });

  it("treats status 0 as a warning and a missing stamp as UNSTAMPED", () => {
    const missing = evaluateFreshness("https://digithings.ai/build-info.json", 0, "", NOW);
    expect(missing.label).toBe("WARN");
    expect(missing.failed).toBe(false);
    const unstamped = evaluateFreshness("https://digithings.ai/build-info.json", 404, "", NOW);
    expect(unstamped.label).toBe("UNSTAMPED");
    expect(unstamped.failed).toBe(true);
  });
});

describe("runSiteProbe", () => {
  it("passes og.png and fails a text/html fallback", async () => {
    const fresh = JSON.stringify({ built_at: "2026-09-30T00:00:00Z" });
    const fetchOk: ProbeFetch = vi.fn(async (url: string) => {
      if (url.endsWith("/og.png")) return response(200, "png", "image/png");
      if (url.endsWith("/graph.json")) return response(200, "{}", "application/json");
      if (url.endsWith("/build-info.json")) return response(200, fresh, "application/json");
      return response(200, "<html></html>", "text/html");
    });

    await expect(runSiteProbe(fetchOk, NOW)).resolves.toEqual({ ok: true });
    const firstInit = (fetchOk as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit;
    const headers = firstInit.headers as Record<string, string>;
    expect(headers["User-Agent"]).toBe(PROBE_USER_AGENT);
    expect(firstInit.signal).toBeInstanceOf(AbortSignal);

    const fetchHtml: ProbeFetch = vi.fn(async (url: string) => {
      if (url === "https://digiquant.io/og.png") return response(200, "<html></html>", "text/html");
      if (url.endsWith("/og.png")) return response(200, "png", "image/png");
      if (url.endsWith("/graph.json")) return response(200, "{}", "application/json");
      if (url.endsWith("/build-info.json")) return response(200, fresh, "application/json");
      return response(200, "<html></html>", "text/html");
    });
    await expect(runSiteProbe(fetchHtml, NOW)).rejects.toThrow(
      "https://digiquant.io/og.png",
    );
  });

  it("fails an asset probe on status 0 and does not call GitHub", async () => {
    const globalFetch = vi.fn();
    vi.stubGlobal("fetch", globalFetch);
    const fetchImpl: ProbeFetch = vi.fn(async (url: string) => {
      if (url === "https://digiquant.io/og.png") {
        throw new Error("network down");
      }
      if (url.endsWith("/og.png")) return response(200, "png", "image/png");
      if (url.endsWith("/graph.json")) return response(200, "{}", "application/json");
      if (url.endsWith("/build-info.json")) {
        return response(200, JSON.stringify({ built_at: "2026-09-30T00:00:00Z" }), "application/json");
      }
      return response(200, "<html></html>", "text/html");
    });
    await expect(runSiteProbe(fetchImpl, NOW)).rejects.toThrow("https://digiquant.io/og.png");
    expect(globalFetch).not.toHaveBeenCalled();
  });
});

describe("runStackProbe", () => {
  it("GETs the three public healthz urls and does not call GitHub", async () => {
    const globalFetch = vi.fn();
    vi.stubGlobal("fetch", globalFetch);
    const seen: string[] = [];
    const fetchImpl: ProbeFetch = vi.fn(async (url: string) => {
      seen.push(url);
      return response(200, JSON.stringify({ ok: true }), "application/json");
    });
    await expect(runStackProbe(fetchImpl)).resolves.toEqual({ ok: true });
    expect(seen).toEqual([
      "https://graph.digithings.ai/healthz",
      "https://key.digithings.ai/healthz",
      "https://search.digithings.ai/healthz",
    ]);
    expect(globalFetch).not.toHaveBeenCalled();
    expect(seen.some((url) => url.includes("api.github.com"))).toBe(false);
  });

  it("warns on 403 and fails when ok is not true", async () => {
    const warned: ProbeFetch = vi.fn(async () => response(403, "challenge", "text/html"));
    await expect(runStackProbe(warned)).resolves.toEqual({ ok: true });

    const bad: ProbeFetch = vi.fn(async (url: string) => {
      if (url === "https://key.digithings.ai/healthz") {
        return response(200, JSON.stringify({ ok: false }), "application/json");
      }
      return response(200, JSON.stringify({ ok: true }), "application/json");
    });
    await expect(runStackProbe(bad)).rejects.toThrow("https://key.digithings.ai/healthz");
  });
});
