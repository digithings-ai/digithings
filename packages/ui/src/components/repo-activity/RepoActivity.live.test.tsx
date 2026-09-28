// @vitest-environment happy-dom
import type { ReactElement } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { REPO_ACTIVITY_DEMO, REPO_ACTIVITY_DEMO_URL } from "./demo";
import { RepoActivity } from "./RepoActivity";

async function mount(ui: ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(ui);
  });
  return {
    host,
    unmount: () => act(() => root.unmount()),
  };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("RepoActivity live fallback", () => {
  it("keeps every snapshot value when the GitHub refresh is not 2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ message: "nope" }), { status: 403 })),
    );
    const { host, unmount } = await mount(
      <RepoActivity
        variant="detailed"
        snapshot={REPO_ACTIVITY_DEMO}
        repoUrl={REPO_ACTIVITY_DEMO_URL}
        live={{ owner: "digithings-ai", repo: "digithings", timeoutMs: 200 }}
      />,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(host.querySelector("[data-source]")?.getAttribute("data-source")).toBe("snapshot");
    expect(host.textContent).toContain("940");
    expect(host.textContent).toContain("snapshot 2026-08-24");
    expect(host.textContent).not.toMatch(/loading/i);
    await unmount();
  });

  it("replaces the snapshot atomically when every GitHub request succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/commits?")) {
          return new Response(JSON.stringify([{ sha: "abc" }]), { status: 200 });
        }
        if (url.includes("is:pr+is:merged")) {
          return new Response(
            JSON.stringify({
              total_count: 12,
              items: [
                {
                  number: 9,
                  title: "live merged",
                  html_url: "https://github.com/digithings-ai/digithings/pull/9",
                  closed_at: "2026-09-02T10:00:00Z",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (url.includes("is:issue+is:closed")) {
          return new Response(JSON.stringify({ total_count: 8, items: [] }), { status: 200 });
        }
        if (url.includes("is:pr+is:open")) {
          return new Response(JSON.stringify({ total_count: 2, items: [] }), { status: 200 });
        }
        if (url.includes("is:issue+is:open")) {
          return new Response(
            JSON.stringify({
              total_count: 3,
              items: [
                {
                  number: 11,
                  title: "live open",
                  html_url: "https://github.com/digithings-ai/digithings/issues/11",
                  updated_at: "2026-09-02T11:00:00Z",
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (url.includes("/releases?")) {
          return new Response(
            JSON.stringify([
              {
                tag_name: "live-tag",
                name: "live",
                published_at: "2026-09-01T00:00:00Z",
                html_url: "https://github.com/digithings-ai/digithings/releases/tag/live-tag",
              },
            ]),
            { status: 200 },
          );
        }
        return new Response("nope", { status: 500 });
      }),
    );
    const { host, unmount } = await mount(
      <RepoActivity
        variant="compact"
        snapshot={REPO_ACTIVITY_DEMO}
        repoUrl={REPO_ACTIVITY_DEMO_URL}
        live={{ owner: "digithings-ai", repo: "digithings", timeoutMs: 400 }}
      />,
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40));
    });
    expect(host.querySelector("[data-source]")?.getAttribute("data-source")).toBe("live");
    expect(host.textContent).toContain("live ");
    expect(host.textContent).toContain("#9");
    expect(host.textContent).not.toContain("940");
    await unmount();
  });
});
