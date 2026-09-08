import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { REPO_ACTIVITY_DEMO, REPO_ACTIVITY_DEMO_CLONE, REPO_ACTIVITY_DEMO_URL } from "./demo";
import { RepoActivity } from "./RepoActivity";

describe("RepoActivity snapshot render", () => {
  it("compact shows the three 30-day metrics, stamp, release, and three PRs — not the backlog", () => {
    const html = renderToStaticMarkup(
      <RepoActivity variant="compact" snapshot={REPO_ACTIVITY_DEMO} repoUrl={REPO_ACTIVITY_DEMO_URL} />,
    );
    expect(html).toContain('data-variant="compact"');
    expect(html).toContain('data-source="snapshot"');
    expect(html).toContain("snapshot 2026-08-24");
    expect(html).toContain("// last 30 days on main");
    expect(html).toContain("940");
    expect(html).toContain("commits");
    expect(html).toContain("546");
    expect(html).toContain("PRs merged");
    expect(html).toContain("605");
    expect(html).toContain("issues closed");
    expect(html).toContain("digichat-v1.3.1");
    expect(html).toContain("#2574");
    expect(html).toContain("#1081");
    expect(html).toContain("#2519");
    expect(html).not.toContain("#2489");
    expect(html).not.toContain("PRs open");
    expect(html).not.toContain("current backlog");
    expect(html).not.toContain("#3445");
    expect(html).not.toMatch(/stars|forks|watchers/i);
  });

  it("detailed separates last-30-days from the current backlog and lists PRs and issues", () => {
    const html = renderToStaticMarkup(
      <RepoActivity
        variant="detailed"
        snapshot={REPO_ACTIVITY_DEMO}
        repoUrl={REPO_ACTIVITY_DEMO_URL}
        cloneCommand={REPO_ACTIVITY_DEMO_CLONE}
        contributingUrl={`${REPO_ACTIVITY_DEMO_URL}/blob/main/CONTRIBUTING.md`}
      />,
    );
    expect(html).toContain('data-variant="detailed"');
    expect(html).toContain("// last 30 days on main");
    expect(html).toContain("// current backlog");
    expect(html).toContain("PRs open");
    expect(html).toContain("issues open");
    expect(html).toContain("// merged recently");
    expect(html).toContain("// open issues");
    expect(html).toContain("#2432");
    expect(html).toContain("#3445");
    expect(html).toContain("git clone https://github.com/digithings-ai/");
    expect(html).toContain("Contributing guide");
    expect(html).not.toMatch(/stars|forks|watchers/i);
  });
});
