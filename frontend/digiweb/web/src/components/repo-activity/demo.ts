import type { RepoActivitySnapshot } from "./types";

/** Realistic fixture for the design-reference specimens. Not live data. */
export const REPO_ACTIVITY_DEMO: RepoActivitySnapshot = {
  generatedAt: "2026-08-24T07:15:49Z",
  windowDays: 30,
  branch: "main",
  commits: 940,
  pullsMerged: 546,
  issuesClosed: 605,
  pullsOpen: 4,
  issuesOpen: 6,
  latestRelease: {
    tag: "digichat-v1.3.1",
    name: "digichat: v1.3.1",
    publishedAt: "2026-08-21T00:49:33Z",
    url: "https://github.com/digithings-ai/digithings/releases/tag/digichat-v1.3.1",
  },
  mergedPulls: [
    {
      number: 2574,
      title: "trade idea continuity, levels ladder, formatting",
      url: "https://github.com/digithings-ai/digithings/pull/2574",
      mergedAt: "2026-08-21T17:35:10Z",
    },
    {
      number: 1081,
      title: "wrap SDCA engine as NautilusTrader strategy",
      url: "https://github.com/digithings-ai/digithings/pull/1081",
      mergedAt: "2026-08-20T22:32:46Z",
    },
    {
      number: 2519,
      title: "add SDCA core engine (composite-risk + accum/dist curve + backtest)",
      url: "https://github.com/digithings-ai/digithings/pull/2519",
      mergedAt: "2026-08-20T13:47:08Z",
    },
    {
      number: 2489,
      title: "book paper fills from the order ledger at the open",
      url: "https://github.com/digithings-ai/digithings/pull/2489",
      mergedAt: "2026-08-19T22:29:27Z",
    },
    {
      number: 2482,
      title: "make H9 append the authoritative commit chain",
      url: "https://github.com/digithings-ai/digithings/pull/2482",
      mergedAt: "2026-08-19T16:06:51Z",
    },
    {
      number: 2432,
      title: "add append-only portfolio lineage ledger schema",
      url: "https://github.com/digithings-ai/digithings/pull/2432",
      mergedAt: "2026-08-17T19:24:40Z",
    },
  ],
  openIssues: [
    {
      number: 3445,
      title: "website: progressively enhance repository section with live GitHub data",
      url: "https://github.com/digithings-ai/digithings/issues/3445",
      updatedAt: "2026-09-02T19:57:46Z",
    },
    {
      number: 3291,
      title: "chore(website): refresh repository activity snapshot",
      url: "https://github.com/digithings-ai/digithings/issues/3291",
      updatedAt: "2026-08-31T09:12:00Z",
    },
    {
      number: 2547,
      title: "worktree task must branch from origin base, not a stale local develop",
      url: "https://github.com/digithings-ai/digithings/issues/2547",
      updatedAt: "2026-08-20T11:04:00Z",
    },
    {
      number: 1981,
      title: "lint and type-check the design-reference workspace in CI",
      url: "https://github.com/digithings-ai/digithings/issues/1981",
      updatedAt: "2026-08-18T16:40:00Z",
    },
    {
      number: 1450,
      title: "promote F1 component families into @digithings/web",
      url: "https://github.com/digithings-ai/digithings/issues/1450",
      updatedAt: "2026-08-12T08:22:00Z",
    },
    {
      number: 1310,
      title: "frontend scoring exception for presentation-only surfaces",
      url: "https://github.com/digithings-ai/digithings/issues/1310",
      updatedAt: "2026-08-08T14:01:00Z",
    },
  ],
};

export const REPO_ACTIVITY_DEMO_URL = "https://github.com/digithings-ai/digithings";
export const REPO_ACTIVITY_DEMO_CLONE = "git clone https://github.com/digithings-ai/digithings";
export const REPO_ACTIVITY_DEMO_CONTRIBUTING =
  "https://github.com/digithings-ai/digithings/blob/main/CONTRIBUTING.md";
