import { describe, expect, it } from "vitest";
import type { RepoModuleRelease } from "@digithings/ui";
import {
  featureFromBody,
  mergeModuleReleases,
  moduleFromTag,
  releasesToModuleReleases,
} from "./moduleReleases";

/**
 * The rail's folding is the only part of the live read that can be checked
 * without a network, so it carries the test weight — the hook itself only wires
 * this to an effect, and its failure path is "keep the committed list".
 */

describe("moduleFromTag", () => {
  it("splits a product tag into module and version", () => {
    expect(moduleFromTag("digichat-v2.3.1")).toEqual({ name: "digichat", version: "2.3.1" });
    expect(moduleFromTag("digiskills-v0.2.1")).toEqual({ name: "digiskills", version: "0.2.1" });
  });

  it("rejects a tag that is not product-vX.Y.Z", () => {
    expect(moduleFromTag("v1.2.3")).toBeNull();
    expect(moduleFromTag("digichat-2.3.1")).toBeNull();
    expect(moduleFromTag("release-2026-09-21")).toBeNull();
  });
});

describe("releasesToModuleReleases", () => {
  it("reduces each product to its newest release", () => {
    const rows = [
      {
        tag_name: "digichat-v2.3.2",
        html_url: "https://github.com/digithings-ai/digithings/releases/tag/digichat-v2.3.2",
        published_at: "2026-09-21T12:38:12Z",
        body: "## [2.3.2](https://example.com)\n\n### Bug Fixes\n\n* **digichat:** hold the fourth turn ([#4460](https://example.com))\n",
      },
      {
        tag_name: "digichat-v2.3.1",
        html_url: "https://github.com/digithings-ai/digithings/releases/tag/digichat-v2.3.1",
        published_at: "2026-09-20T10:50:02Z",
        body: "",
      },
      {
        tag_name: "digiskills-v0.2.1",
        html_url: "https://github.com/digithings-ai/digithings/releases/tag/digiskills-v0.2.1",
        published_at: "2026-08-17T20:24:31Z",
        body: "",
      },
    ];
    expect(releasesToModuleReleases(rows)).toEqual([
      {
        name: "digichat",
        version: "2.3.2",
        url: "https://github.com/digithings-ai/digithings/releases/tag/digichat-v2.3.2",
        date: "2026-09-21",
        title: "hold the fourth turn",
      },
      {
        name: "digiskills",
        version: "0.2.1",
        url: "https://github.com/digithings-ai/digithings/releases/tag/digiskills-v0.2.1",
        date: "2026-08-17",
      },
    ]);
  });

  it("drops drafts, malformed rows and rows with no usable tag", () => {
    const rows = [
      { tag_name: "digichat-v9.9.9", draft: true, published_at: "2026-10-01T00:00:00Z" },
      { tag_name: "not-a-product-tag", published_at: "2026-10-01T00:00:00Z" },
      "nope",
      null,
      { tag_name: "digichat-v2.3.2", published_at: "2026-09-21T12:38:12Z" },
    ];
    const out = releasesToModuleReleases(rows);
    expect(out.map((r) => r.version)).toEqual(["2.3.2"]);
  });

  it("treats a non-array payload as no releases", () => {
    expect(releasesToModuleReleases({ message: "rate limited" })).toEqual([]);
    expect(releasesToModuleReleases(null)).toEqual([]);
  });
});

describe("featureFromBody", () => {
  it("takes the first bullet and strips the changelog syntax", () => {
    const body =
      "## [2.3.1](https://example.com) (2026-09-20)\n\n### Bug Fixes\n\n* **digichat:** the embed paints one canvas token from the first byte ([#4433](https://example.com)) ([dea7717](https://example.com))\n";
    expect(featureFromBody(body)).toBe("the embed paints one canvas token from the first byte");
  });

  it("falls back to a hand-written prose body", () => {
    expect(featureFromBody("Embed free-turn gate fix (#4460): the send button submits.\n")).toBe(
      "Embed free-turn gate fix: the send button submits",
    );
  });

  it("returns undefined when there is nothing to call out", () => {
    expect(featureFromBody("")).toBeUndefined();
    expect(featureFromBody(null)).toBeUndefined();
    expect(featureFromBody("### Bug Fixes\n")).toBeUndefined();
  });
});

describe("mergeModuleReleases", () => {
  const fallback: RepoModuleRelease[] = [
    { name: "digichat", version: "2.3.2" },
    { name: "digigraph", version: "0.1.0" },
    { name: "digiskills", version: "0.2.1" },
  ];

  it("overlays live releases on the declared list, keeping its order", () => {
    const live: RepoModuleRelease[] = [
      { name: "digiskills", version: "0.2.1", date: "2026-08-17", title: "uv dependency-group" },
      { name: "digichat", version: "2.3.2", date: "2026-09-21", title: "hold the fourth turn" },
    ];
    expect(mergeModuleReleases(fallback, live)).toEqual([
      { name: "digichat", version: "2.3.2", date: "2026-09-21", title: "hold the fourth turn" },
      { name: "digigraph", version: "0.1.0" },
      { name: "digiskills", version: "0.2.1", date: "2026-08-17", title: "uv dependency-group" },
    ]);
  });

  it("ignores a live product the rail does not know about", () => {
    const live: RepoModuleRelease[] = [{ name: "digiunknown", version: "1.0.0" }];
    expect(mergeModuleReleases(fallback, live)).toEqual(fallback);
  });
});
