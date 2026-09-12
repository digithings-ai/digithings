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
    {
      number: 2398,
      title: "rate-limit live refresh behind a shared budget",
      url: "https://github.com/digithings-ai/digithings/pull/2398",
      mergedAt: "2026-08-14T11:02:19Z",
    },
    {
      number: 2381,
      title: "collapse two-column activity on narrow screens",
      url: "https://github.com/digithings-ai/digithings/pull/2381",
      mergedAt: "2026-08-11T15:44:52Z",
    },
    {
      number: 2377,
      title: "hairline lists for merged PRs and open issues",
      url: "https://github.com/digithings-ai/digithings/pull/2377",
      mergedAt: "2026-08-11T09:18:03Z",
    },
    {
      number: 2355,
      title: "snapshot-first velocity with atomic live swap",
      url: "https://github.com/digithings-ai/digithings/pull/2355",
      mergedAt: "2026-08-06T20:31:47Z",
    },
    {
      number: 2319,
      title: "mono numerals with tabular figures",
      url: "https://github.com/digithings-ai/digithings/pull/2319",
      mergedAt: "2026-07-30T14:09:55Z",
    },
    {
      number: 2314,
      title: "kicker grammar across data specimens",
      url: "https://github.com/digithings-ai/digithings/pull/2314",
      mergedAt: "2026-07-29T18:52:36Z",
    },
    {
      number: 2290,
      title: "clone-box geometry that keeps beating utilities",
      url: "https://github.com/digithings-ai/digithings/pull/2290",
      mergedAt: "2026-07-24T10:27:11Z",
    },
    {
      number: 2271,
      title: "design tokens bridge for reference and web",
      url: "https://github.com/digithings-ai/digithings/pull/2271",
      mergedAt: "2026-07-17T16:40:28Z",
    },
    {
      number: 2244,
      title: "no stars, forks, or watchers on activity",
      url: "https://github.com/digithings-ai/digithings/pull/2244",
      mergedAt: "2026-07-10T12:14:59Z",
    },
    {
      number: 2210,
      title: "compact card for portfolio surfaces",
      url: "https://github.com/digithings-ai/digithings/pull/2210",
      mergedAt: "2026-07-02T09:33:22Z",
    },
    {
      number: 2187,
      title: "detailed view with backlog split",
      url: "https://github.com/digithings-ai/digithings/pull/2187",
      mergedAt: "2026-06-25T21:48:07Z",
    },
    {
      number: 2179,
      title: "release link with honest timestamps",
      url: "https://github.com/digithings-ai/digithings/pull/2179",
      mergedAt: "2026-06-25T08:05:41Z",
    },
    {
      number: 2152,
      title: "copy button for the clone command",
      url: "https://github.com/digithings-ai/digithings/pull/2152",
      mergedAt: "2026-06-18T13:57:30Z",
    },
    {
      number: 2118,
      title: "first activity snapshot fixture",
      url: "https://github.com/digithings-ai/digithings/pull/2118",
      mergedAt: "2026-06-11T17:22:54Z",
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
  /** Synthetic 14-day series so the specimen shows graded cells. Not live data. */
  dailyContributions: [
    { date: "2026-08-11", count: 1 },
    { date: "2026-08-12", count: 3 },
    { date: "2026-08-13", count: 2 },
    { date: "2026-08-14", count: 6 },
    { date: "2026-08-15", count: 1 },
    { date: "2026-08-16", count: 4 },
    { date: "2026-08-17", count: 8 },
    { date: "2026-08-18", count: 2 },
    { date: "2026-08-19", count: 5 },
    { date: "2026-08-20", count: 3 },
    { date: "2026-08-21", count: 9 },
    { date: "2026-08-22", count: 1 },
    { date: "2026-08-23", count: 4 },
    { date: "2026-08-24", count: 7 },
  ],
};

export const REPO_ACTIVITY_DEMO_URL = "https://github.com/digithings-ai/digithings";
export const REPO_ACTIVITY_DEMO_CLONE = "git clone https://github.com/digithings-ai/digithings";
export const REPO_ACTIVITY_DEMO_CONTRIBUTING =
  "https://github.com/digithings-ai/digithings/blob/main/CONTRIBUTING.md";
