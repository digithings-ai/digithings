/**
 * Showcase copy for digiquant-web (#4895). This site is the marketing product
 * story — not the operator dashboard. The dashboard owns the live tool surface.
 */
import type { NavItem, NavLink, NumberedStage, OdometerStat } from "@digithings/ui";

export const SHOWCASE_NAV: NavItem[] = [
  { label: "Desk", href: "/#desk" },
  { label: "Method", href: "/#method" },
  { label: "Watch", href: "/#watch" },
  { label: "Partners", href: "/#partners" },
  { label: "Story", href: "/#story" },
];

export const SHOWCASE_FOOTER: NavLink[] = [
  { label: "Desk", href: "/#desk" },
  { label: "Method", href: "/#method" },
  { label: "Watch", href: "/#watch" },
  { label: "Partners", href: "/#partners" },
  { label: "Story", href: "/#story" },
  { label: "Published research", href: "/strategies" },
  { label: "Changelog", href: "/changelog" },
  { label: "Contact", href: "/contact" },
  { label: "Built on digithings", href: "https://digithings.ai", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const SHOWCASE_METRICS: OdometerStat[] = [
  { value: "3", label: "subsystems" },
  { value: "0", label: "live venues" },
];

export const METHOD_STAGES: NumberedStage[] = [
  {
    num: "01",
    title: "Method",
    tag: "research",
    mech: "Daily research runs, a decision log per run, and a tearsheet you can audit — not a black box.",
  },
  {
    num: "02",
    title: "Tooling",
    tag: "mcp · nautilus",
    mech: "MCP tools, broker research mirrors, and NautilusTrader backtests. The dashboard is where they run.",
  },
  {
    num: "03",
    title: "Workflow",
    tag: "compose → inspect",
    mech: "Describe a sleeve in digichat, backtest it, read the tearsheet, journal the call.",
  },
  {
    num: "04",
    title: "Capabilities",
    tag: "in-app",
    mech: "Strategy builder, strategies, trade journaling, and partner integrations live in the dashboard — this site shows them.",
  },
];

export const STORY_STAGES: NumberedStage[] = [
  {
    num: "01",
    title: "digichat",
    tag: "compose",
    mech: "Describe the idea in the desk chat. The builder itself is the dashboard, not this page.",
  },
  {
    num: "02",
    title: "Nautilus backtest",
    tag: "research path",
    mech: "The research graph hands the sleeve to NautilusTrader. Paper marks, not a venue.",
  },
  {
    num: "03",
    title: "Inspect",
    tag: "tearsheet",
    mech: "Read the run, journal the call, keep the decision on the record.",
  },
  {
    num: "04",
    title: "Hand off",
    tag: "demo narrative",
    mech: "Deploy is a story beat on this site. Routing to a live venue is off.",
  },
];

export const VIDEO_SLOTS = [
  {
    id: "method",
    kicker: "01",
    title: "Method",
    body: "How the research graph thinks, and what a run leaves on the record.",
  },
  {
    id: "capabilities",
    kicker: "02",
    title: "Capabilities",
    body: "Strategy, journal, and the tool surface — shown, not reimplemented here.",
  },
  {
    id: "arc",
    kicker: "03",
    title: "Chat to backtest",
    body: "digichat compose, Nautilus run, tearsheet. Film forthcoming.",
  },
] as const;

export const PARTNER_SLOTS = [
  {
    id: "luxalgo",
    kicker: "chart · data",
    title: "LuxAlgo",
    body: "Research chart and market-tracker backbone. Embed lands here when the partner cut is ready.",
  },
  {
    id: "gloomberg",
    kicker: "tape · desk",
    title: "Gloomberg",
    body: "The tape language the dashboard will speak. Placeholder for a partner story embed.",
  },
] as const;

export const DESK_TOUR = {
  caption: "Dashboard display — the builder, journal, and tools live in-app.",
  mode: "paper",
  surfaces: ["house", "research", "journal", "tools"] as const,
  prompt: "Describe a mean-reversion sleeve on BTC.",
  book: [
    { symbol: "BTC", sleeve: "mean-rev", state: "paper" },
    { symbol: "ETH", sleeve: "trend", state: "paper" },
    { symbol: "SOL", sleeve: "breakout", state: "paper" },
  ] as const,
  journal: [
    { when: "09-30", note: "Sized after the drawdown bound." },
    { when: "09-28", note: "Backtest closed. Kept the sleeve." },
    { when: "09-21", note: "Dropped the overlapping overlay." },
  ] as const,
};

/** Marketing copy must not claim live trading or revive retired module names. */
export const FORBIDDEN_SHOWCASE_CLAIM =
  /\blive[\s-]?trad(?:e|ing)\b|\bsend orders\b|Olympus|Atlas|Hermes|Kairos/i;
