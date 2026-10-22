import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEPLOY_BRANCH,
  DEPLOY_COMMIT_PATCH_URL,
  DEPLOY_REMOTE_FEED_URL,
  DEPLOY_REMOTE_REFS_URL,
  DEPLOY_SITE_URL,
  evaluateDeployCommit,
  evaluateFreshness,
  oldestUnbuiltCommit,
  parseCommitFeed,
  parseCommitPatchDate,
  parseRemoteRef,
  PROBE_USER_AGENT,
  runDeployProbe,
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
  it("GETs the three worker-only status urls and does not call GitHub", async () => {
    const globalFetch = vi.fn();
    vi.stubGlobal("fetch", globalFetch);
    const seen: string[] = [];
    const fetchImpl: ProbeFetch = vi.fn(async (url: string) => {
      seen.push(url);
      return response(200, JSON.stringify({ ok: true }), "application/json");
    });
    await expect(runStackProbe(fetchImpl)).resolves.toEqual({ ok: true });
    expect(seen).toEqual([
      "https://graph.digithings.ai/_stack/status",
      "https://key.digithings.ai/_stack/status",
      "https://search.digithings.ai/_stack/status",
    ]);
    expect(globalFetch).not.toHaveBeenCalled();
    expect(seen.some((url) => url.includes("api.github.com"))).toBe(false);
  });

  it("warns on 403 and fails when ok is not true", async () => {
    const warned: ProbeFetch = vi.fn(async () => response(403, "challenge", "text/html"));
    await expect(runStackProbe(warned)).resolves.toEqual({ ok: true });

    const bad: ProbeFetch = vi.fn(async (url: string) => {
      if (url === "https://key.digithings.ai/_stack/status") {
        return response(200, JSON.stringify({ ok: false }), "application/json");
      }
      return response(200, JSON.stringify({ ok: true }), "application/json");
    });
    await expect(runStackProbe(bad)).rejects.toThrow("https://key.digithings.ai/_stack/status");
  });
});

/* --- deploy freshness (DIG-4871) ---------------------------------------- */

const DEPLOY_NOW = new Date("2026-10-22T06:30:00Z");
const MAIN_SHA = "eef1ee72c20f9dddf097033fcaa48fd7a054a0e6";
const SERVED_SHA = "7de39ec9a0ed417154258c4d993c9924421e2a18";
/** The tip of main at the time of writing (moved minutes before the probe). */
const TIP_SHA = "9218e1f70149a47d2855e0958019108f93b94481";
/** The first main commit production never built - the start of the break. */
const ANCHOR_SHA = "977aa17438aea8fc8b82200c78e64fb152626da5";
/** The newest main commit that is still older than the served build. */
const MID_SHA = "8027726510f7ee1b3b1e0ecb0e8ca3b4c2e2f5c4";

/** A pkt-line ref advertisement shaped like the one the public remote serves. */
function refAdvertisement(mainSha: string): string {
  return [
    "0000",
    "0015ca1c25d2df75b4eb250be8b7728320eb799495959 HEAD\u0000multi_ack thin-pack",
    `003d${mainSha} refs/heads/main\n`,
    "0054045e6151111111111111111111111111111111111111111111111111111111111111 refs/heads/other\n",
  ].join("");
}

/** The public atom commit feed of main, newest first. */
function feedBody(entries: Array<{ sha: string; updated: string }>): string {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<feed xmlns="http://www.w3.org/2005/Atom">',
    ...entries.map((entry) =>
      [
        "<entry>",
        `  <id>tag:github.com,2008:Grit::Commit/${entry.sha}</id>`,
        `  <updated>${entry.updated}</updated>`,
        "  <title>chore: promote develop to main</title>",
        "</entry>",
      ].join("\n"),
    ),
    "</feed>",
  ].join("\n");
}

/** The feed as the public remote serves it: tip, the missed commit, the served one. */
function liveFeedBody(): string {
  return feedBody([
    { sha: TIP_SHA, updated: "2026-10-22T06:18:35Z" },
    { sha: ANCHOR_SHA, updated: "2026-10-20T18:35:15Z" },
    { sha: SERVED_SHA, updated: "2026-10-13T10:41:57Z" },
  ]);
}

function patchBody(date: string): string {
  return [
    `From ${MAIN_SHA} Mon Sep 17 00:00:00 2001`,
    "From: Chris <chris@example.com>",
    `Date: ${date}`,
    "Subject: [PATCH] chore: promote develop to main",
    "",
    "diff --git a/README.md b/README.md",
  ].join("\n");
}

describe("parseRemoteRef", () => {
  it("reads the sha of refs/heads/main out of the pkt-line advertisement", () => {
    expect(parseRemoteRef(refAdvertisement(MAIN_SHA))).toBe(MAIN_SHA);
  });

  it("does not read a longer ref name that starts with main", () => {
    const body = `003d${MAIN_SHA} refs/heads/mainline\n`;
    expect(parseRemoteRef(body)).toBeNull();
  });

  it("returns null when the advertisement carries no main ref", () => {
    expect(parseRemoteRef("0000nothing here\n")).toBeNull();
  });
});

describe("parseCommitPatchDate", () => {
  it("reads the mbox Date header and normalises it to UTC", () => {
    expect(parseCommitPatchDate(patchBody("Thu, 22 Oct 2026 01:59:00 +0200"))).toBe(
      "2026-10-21T23:59:00Z",
    );
  });

  it("returns null when the patch carries no Date header", () => {
    expect(parseCommitPatchDate("Subject: [PATCH] nothing\n")).toBeNull();
  });
});

describe("parseCommitFeed", () => {
  it("reads the sha and the date of every entry, newest first", () => {
    const feed = parseCommitFeed(
      feedBody([
        { sha: TIP_SHA, updated: "2026-10-22T06:18:35Z" },
        { sha: SERVED_SHA, updated: "2026-10-13T10:41:57Z" },
      ]),
    );
    expect(feed).toEqual([
      { sha: TIP_SHA, updated: "2026-10-22T06:18:35Z" },
      { sha: SERVED_SHA, updated: "2026-10-13T10:41:57Z" },
    ]);
  });

  it("returns an empty feed when the body is not a feed", () => {
    expect(parseCommitFeed("<html>not a feed</html>")).toEqual([]);
  });
});

describe("oldestUnbuiltCommit", () => {
  it("names the first main commit production did not build", () => {
    const feed = parseCommitFeed(liveFeedBody());
    expect(oldestUnbuiltCommit(feed, SERVED_SHA, "2026-10-13T10:45:05Z")).toEqual({
      sha: ANCHOR_SHA,
      updated: "2026-10-20T18:35:15Z",
    });
  });

  it("falls back to the oldest entry newer than the served build when the served commit left the window", () => {
    const feed = parseCommitFeed(
      feedBody([
        { sha: TIP_SHA, updated: "2026-10-22T06:18:35Z" },
        { sha: MID_SHA, updated: "2026-10-21T12:00:00Z" },
      ]),
    );
    expect(oldestUnbuiltCommit(feed, SERVED_SHA, "2026-10-13T10:45:05Z")).toEqual({
      sha: MID_SHA,
      updated: "2026-10-21T12:00:00Z",
    });
  });

  it("returns null when nothing in the feed is newer than the served build", () => {
    const feed = parseCommitFeed(
      feedBody([{ sha: MID_SHA, updated: "2026-10-12T00:00:00Z" }]),
    );
    expect(oldestUnbuiltCommit(feed, SERVED_SHA, "2026-10-13T10:45:05Z")).toBeNull();
  });

  it("returns null for an empty feed", () => {
    expect(oldestUnbuiltCommit([], SERVED_SHA, "2026-10-13T10:45:05Z")).toBeNull();
  });
});

describe("evaluateDeployCommit", () => {
  const stamp = {
    commit: SERVED_SHA,
    builtAt: "2026-10-13T10:45:05Z",
    detail: "built_at=2026-10-13T10:45:05Z",
  };

  it("passes when production serves the production branch tip", () => {
    const verdict = evaluateDeployCommit(
      { ...stamp, commit: MAIN_SHA },
      { commit: MAIN_SHA, committedAt: "2026-10-21T23:59:00Z" },
      DEPLOY_NOW,
    );
    expect(verdict.label).toBe("PASS");
    expect(verdict.failed).toBe(false);
  });

  it("fails when main moved long ago and production still serves the old build", () => {
    const verdict = evaluateDeployCommit(
      stamp,
      { commit: MAIN_SHA, committedAt: "2026-10-19T10:45:05Z" },
      DEPLOY_NOW,
    );
    expect(verdict.label).toBe("FAIL");
    expect(verdict.failed).toBe(true);
    expect(verdict.message).toContain(MAIN_SHA);
    expect(verdict.message).toContain(SERVED_SHA);
  });

  it("warns, and does not fail, while a build for the new commit may still be in flight", () => {
    const verdict = evaluateDeployCommit(
      stamp,
      { commit: MAIN_SHA, committedAt: "2026-10-22T04:00:00Z" },
      DEPLOY_NOW,
    );
    expect(verdict.label).toBe("WARN");
    expect(verdict.failed).toBe(false);
  });

  it("never fails on its own transport: an unreadable remote decides nothing", () => {
    const verdict = evaluateDeployCommit(
      stamp,
      { commit: null, committedAt: null },
      DEPLOY_NOW,
    );
    expect(verdict.label).toBe("WARN");
    expect(verdict.failed).toBe(false);
  });

  it("never fails on a missing stamp: the site probe owns that signal", () => {
    const verdict = evaluateDeployCommit(
      { commit: null, builtAt: null, detail: "HTTP 404" },
      { commit: MAIN_SHA, committedAt: "2026-10-19T10:45:05Z" },
      DEPLOY_NOW,
    );
    expect(verdict.label).toBe("WARN");
    expect(verdict.failed).toBe(false);
  });

  it("anchors the grace on the first unbuilt commit, not on the tip", () => {
    // The tip moved 11 minutes ago, the break started 36 hours ago: a grace
    // anchored on the tip would hide the break behind the last main move.
    const verdict = evaluateDeployCommit(
      stamp,
      {
        commit: TIP_SHA,
        committedAt: "2026-10-22T06:18:35Z",
        unbuiltCommit: ANCHOR_SHA,
        unbuiltAt: "2026-10-20T18:35:15Z",
      },
      DEPLOY_NOW,
    );
    expect(verdict.label).toBe("FAIL");
    expect(verdict.failed).toBe(true);
    expect(verdict.message).toContain(ANCHOR_SHA);
    expect(verdict.message).toContain(SERVED_SHA);
  });

  it("warns while a build for the first unbuilt commit may still be in flight", () => {
    const verdict = evaluateDeployCommit(
      stamp,
      {
        commit: TIP_SHA,
        committedAt: "2026-10-22T06:18:35Z",
        unbuiltCommit: ANCHOR_SHA,
        unbuiltAt: "2026-10-22T04:00:00Z",
      },
      DEPLOY_NOW,
    );
    expect(verdict.label).toBe("WARN");
    expect(verdict.failed).toBe(false);
  });
});

describe("runDeployProbe", () => {
  it("reads the stamp, the public git remote and the commit feed, and fails on a stale deploy", async () => {
    const globalFetch = vi.fn();
    vi.stubGlobal("fetch", globalFetch);
    const seen: string[] = [];
    const fetchImpl: ProbeFetch = vi.fn(async (url: string) => {
      seen.push(url);
      if (url === DEPLOY_SITE_URL) {
        return response(
          200,
          JSON.stringify({
            site: "digiquant.io",
            commit: SERVED_SHA,
            branch: "main",
            builder: "cloudflare-pages",
            built_at: "2026-10-13T10:45:05Z",
          }),
          "application/json",
        );
      }
      if (url === DEPLOY_REMOTE_REFS_URL) {
        return response(200, refAdvertisement(TIP_SHA), "application/x-git-upload-pack-advertisement");
      }
      if (url === DEPLOY_REMOTE_FEED_URL) {
        return response(200, liveFeedBody(), "application/atom+xml");
      }
      return response(404, "", "text/plain");
    });

    await expect(runDeployProbe(fetchImpl, DEPLOY_NOW)).rejects.toThrow(
      "digiquant.io still serves",
    );
    expect(seen[0]).toBe(DEPLOY_SITE_URL);
    expect(seen[1]).toBe(DEPLOY_REMOTE_REFS_URL);
    expect(seen[2]).toBe(DEPLOY_REMOTE_FEED_URL);
    expect(seen.some((url) => url.includes("api.github.com"))).toBe(false);
    expect(globalFetch).not.toHaveBeenCalled();
  });

  it("names the commit production missed first, not the tip", async () => {
    const fetchImpl: ProbeFetch = vi.fn(async (url: string) => {
      if (url === DEPLOY_SITE_URL) {
        return response(
          200,
          JSON.stringify({ commit: SERVED_SHA, built_at: "2026-10-13T10:45:05Z" }),
          "application/json",
        );
      }
      if (url === DEPLOY_REMOTE_REFS_URL) {
        return response(200, refAdvertisement(TIP_SHA), "application/x-git-upload-pack-advertisement");
      }
      if (url === DEPLOY_REMOTE_FEED_URL) {
        return response(200, liveFeedBody(), "application/atom+xml");
      }
      return response(404, "", "text/plain");
    });

    await expect(runDeployProbe(fetchImpl, DEPLOY_NOW)).rejects.toThrow(ANCHOR_SHA);
  });

  it("passes when the live stamp already carries the production branch tip", async () => {
    const fetchImpl: ProbeFetch = vi.fn(async (url: string) => {
      if (url === DEPLOY_SITE_URL) {
        return response(
          200,
          JSON.stringify({ commit: MAIN_SHA, built_at: "2026-10-22T05:00:00Z" }),
          "application/json",
        );
      }
      if (url === DEPLOY_REMOTE_REFS_URL) {
        return response(200, refAdvertisement(MAIN_SHA), "application/x-git-upload-pack-advertisement");
      }
      return response(404, "", "text/plain");
    });
    await expect(runDeployProbe(fetchImpl, DEPLOY_NOW)).resolves.toEqual({ ok: true });
  });

  it("falls back to the tip date when the feed cannot be read, and asks for the first kilobyte only", async () => {
    const fetchImpl: ProbeFetch = vi.fn(async (url: string) => {
      if (url === DEPLOY_SITE_URL) {
        return response(
          200,
          JSON.stringify({ commit: SERVED_SHA, built_at: "2026-10-13T10:45:05Z" }),
          "application/json",
        );
      }
      if (url === DEPLOY_REMOTE_REFS_URL) {
        return response(200, refAdvertisement(TIP_SHA), "application/x-git-upload-pack-advertisement");
      }
      if (url === DEPLOY_REMOTE_FEED_URL) {
        return response(500, "", "text/plain");
      }
      return response(206, patchBody("Wed, 21 Oct 2026 01:59:00 +0200"), "text/plain");
    });
    await expect(runDeployProbe(fetchImpl, DEPLOY_NOW)).rejects.toThrow();
    const patchCall = (fetchImpl as ReturnType<typeof vi.fn>).mock.calls.find((call) =>
      String(call[0]).endsWith(".patch"),
    );
    const init = patchCall?.[1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers.Range).toBe("bytes=0-1023");
  });

  it("decides nothing when the remote cannot be read", async () => {
    const fetchImpl: ProbeFetch = vi.fn(async (url: string) => {
      if (url === DEPLOY_SITE_URL) {
        return response(
          200,
          JSON.stringify({ commit: SERVED_SHA, built_at: "2026-10-13T10:45:05Z" }),
          "application/json",
        );
      }
      return response(500, "", "text/plain");
    });
    await expect(runDeployProbe(fetchImpl, DEPLOY_NOW)).resolves.toEqual({ ok: true });
  });

  it("names the branch it compares against", () => {
    expect(DEPLOY_BRANCH).toBe("main");
  });
});
