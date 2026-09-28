import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchRepoActivityLive } from "./fetch";
import type { RepoActivityLiveConfig } from "./types";

const CFG: RepoActivityLiveConfig = {
  owner: "digithings-ai",
  repo: "digithings",
  branch: "main",
  windowDays: 30,
  timeoutMs: 250,
};

type Json = Record<string, unknown> | unknown[];

function jsonResponse(body: Json, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function searchHits(total: number, items: Json[] = []) {
  return { total_count: total, incomplete_results: false, items };
}

const MERGED_ITEMS = [
  {
    number: 3187,
    title: "feat(digiquant): GET profile + Settings profile hydrate",
    html_url: "https://github.com/digithings-ai/digithings/pull/3187",
    closed_at: "2026-08-30T12:00:00Z",
    updated_at: "2026-08-30T12:00:00Z",
  },
];

const OPEN_ISSUE_ITEMS = [
  {
    number: 3445,
    title: "website: progressively enhance repository section with live GitHub data",
    html_url: "https://github.com/digithings-ai/digithings/issues/3445",
    updated_at: "2026-09-02T19:57:46Z",
  },
];

function okByUrl(url: string): Response {
  if (url.includes("/commits?")) {
    return jsonResponse([], 200, {
      Link: '<https://api.github.com/repos/digithings-ai/digithings/commits?page=940&per_page=1>; rel="last"',
    });
  }
  if (url.includes("is:pr+is:merged")) {
    return jsonResponse(searchHits(546, MERGED_ITEMS));
  }
  if (url.includes("is:issue+is:closed")) {
    return jsonResponse(searchHits(605));
  }
  if (url.includes("is:pr+is:open")) {
    return jsonResponse(searchHits(4));
  }
  if (url.includes("is:issue+is:open")) {
    return jsonResponse(searchHits(6, OPEN_ISSUE_ITEMS));
  }
  if (url.includes("/releases?")) {
    return jsonResponse([
      {
        tag_name: "digichat-v1.3.1",
        name: "digichat: v1.3.1",
        published_at: "2026-08-21T00:49:33Z",
        html_url: "https://github.com/digithings-ai/digithings/releases/tag/digichat-v1.3.1",
      },
    ]);
  }
  return jsonResponse({ message: "unexpected " + url }, 500);
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("fetchRepoActivityLive", () => {
  it("applies a successful GitHub refresh atomically", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => okByUrl(String(input)));
    const live = await fetchRepoActivityLive({
      ...CFG,
      fetch,
      now: () => new Date("2026-09-02T20:00:00Z"),
    });

    expect(live.commits).toBe(940);
    expect(live.pullsMerged).toBe(546);
    expect(live.issuesClosed).toBe(605);
    expect(live.pullsOpen).toBe(4);
    expect(live.issuesOpen).toBe(6);
    expect(live.branch).toBe("main");
    expect(live.windowDays).toBe(30);
    expect(live.generatedAt).toBe("2026-09-02T20:00:00Z");
    expect(live.latestRelease?.tag).toBe("digichat-v1.3.1");
    expect(live.mergedPulls).toEqual([
      {
        number: 3187,
        title: "feat(digiquant): GET profile + Settings profile hydrate",
        url: "https://github.com/digithings-ai/digithings/pull/3187",
        mergedAt: "2026-08-30T12:00:00Z",
      },
    ]);
    expect(live.openIssues[0]?.number).toBe(3445);
    expect(JSON.stringify(live)).not.toMatch(/stars|forks|watchers/i);

    const urls = fetch.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("sha=main") && u.includes("since="))).toBe(true);
    expect(urls.some((u) => u.includes("is:pr+is:open") && !u.includes("created:"))).toBe(true);
    expect(urls.some((u) => u.includes("is:issue+is:open") && u.includes("sort=updated"))).toBe(
      true,
    );
  });

  it("counts a single-page commit window from the body length", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/commits?")) {
        return jsonResponse([{ sha: "abc" }]);
      }
      return okByUrl(url);
    });
    const live = await fetchRepoActivityLive({ ...CFG, fetch });
    expect(live.commits).toBe(1);
  });

  it("rejects a timeout without returning a partial payload", async () => {
    const fetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      return new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });
    await expect(fetchRepoActivityLive({ ...CFG, timeoutMs: 20, fetch })).rejects.toThrow(
      /timeout|abort/i,
    );
  });

  it("rejects a non-2xx response", async () => {
    const fetch = vi.fn(async () => jsonResponse({ message: "nope" }, 403));
    await expect(fetchRepoActivityLive({ ...CFG, fetch })).rejects.toThrow(/403/);
  });

  it("rejects a malformed search payload", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("is:pr+is:merged")) {
        return jsonResponse({ items: "nope" });
      }
      return okByUrl(url);
    });
    await expect(fetchRepoActivityLive({ ...CFG, fetch })).rejects.toThrow(/malformed/i);
  });

  it("treats an empty releases list as no latest release, not a failure", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/releases?")) return jsonResponse([]);
      return okByUrl(url);
    });
    const live = await fetchRepoActivityLive({ ...CFG, fetch });
    expect(live.latestRelease).toBeNull();
  });
});
