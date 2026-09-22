import {
  CtaLink,
  Mono,
  ReleaseRail,
  RepoHeatmap,
  TestimonialWall,
  type ReleaseRailItem,
  type TestimonialQuote,
} from "@digithings/ui";
import releases from "@digithings/design/releases.json";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_URL, repoActivity } from "@/lib/repoActivity";
import { GROUPED_LABEL } from "./label";

/**
 * The open-source band, the FAQ and the voices (v12 → v15, #4429).
 *
 * The repo view responds to the owner's note that the section "seems a little
 * heavy... very dense relative to the rest of the website" and to their later
 * direction: "show the grid of the activity on the repo like we used to have.
 * I just keep it more simple... just simply what the activity has been. Any new
 * releases." The heatmap is cut to six months (`weeks={26}`) rather than a full
 * year, and depth lives behind a link to /changelog.
 *
 * The alternative repo variants (`RepoCompact`, `RepoCloneFirst`) and the three
 * digiquant variants that used to live here (`QuantPipeline`, `QuantFrame`,
 * `QuantSplit`) were retired once the Boot band and the digiquant band were
 * rebuilt — the live bands are `BootTerminal` and `QuantSection`, and the dead
 * exports only made this file harder to read. The hand-rolled two-blockquote
 * `Quotes` band is gone too: it is now `Testimonials`, one `TestimonialWall`
 * (v15 point 5).
 */

// ═══ Repository ═════════════════════════════════════════════════════════════

// A six-month window, not a year. `RepoActivity variant="detailed"` hard-codes
// 53 weeks, so the six-month cut calls RepoHeatmap directly — the primitive is
// exported and its "the last N weeks" label adapts to whatever `weeks` says.
//
// The total in that label is summed over every cell it is handed, not clipped
// to `weeks`, so the series must be sliced here first: the snapshot carries 371
// days (a year plus a day) and passing all of it under `weeks={26}` would print
// a 26-week heading above a 53-week total. Trim to the last `weeks * 7` days —
// the primitive indexes `days[0]`/`days[days.length - 1]` for its range, so the
// slice also has to be what defines the grid.
const HEATMAP_WEEKS = 26;
const HEATMAP_DAYS = (repoActivity.dailyContributions ?? []).slice(-HEATMAP_WEEKS * 7);

// ── Activity grid (the owner's pick) ────────────────────────────────────────
// The contribution grid plus the few signals that say "and it is still moving":
// the last release, and a link to the changelog for anyone who wants the detail
// rather than a summary of it.
//
// The counted-signal row wears the repo primitives' own mono meta scale
// (`0.78rem`, as `.ra-release` / `.ra-repo` / `.ra-cta a` do in
// `repo-activity.css`) so it reads as the same ledger as the rest of the repo
// vocabulary rather than as a caption that drifted.
export function RepoGrid() {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-[1.8rem]">
      {/* The heatmap's coordinate frame is width:max-content (deliberately —
          repo-activity.css explains why capping it reintroduces month-label
          drift), so its min-content is the full 26-week grid plus the days
          gutter. Below ~420px that is wider than the padded column, and an
          implicit `auto` track would take the min-content and push the whole
          page sideways. minmax(0,1fr) + min-w-0 pins the track instead, so
          `.ra-heat-body`'s own overflow-x:auto does the scrolling. */}
      <RepoHeatmap
        pulls={repoActivity.mergedPulls}
        data={HEATMAP_DAYS}
        weeks={HEATMAP_WEEKS}
        className="min-w-0"
      />
      <div className="flex flex-wrap items-baseline gap-x-[2rem] gap-y-[0.6rem] font-mono text-[0.78rem] text-ink-soft">
        <span>
          <Mono>{repoActivity.latestRelease?.tag ?? "—"}</Mono> latest release
        </span>
        <span>
          <Mono>{repoActivity.pullsMerged.toLocaleString("en-US")}</Mono> pulls merged
        </span>
        <span>
          <Mono>{repoActivity.issuesClosed.toLocaleString("en-US")}</Mono> issues closed
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-[0.8rem]">
        <CtaLink href="/changelog">Full changelog</CtaLink>
        <CtaLink href={REPO_URL} external variant="ghost">
          Browse the repository
        </CtaLink>
      </div>
    </div>
  );
}

// ═══ FAQ ════════════════════════════════════════════════════════════════════

// Answers are drawn from /security, /quality and /legal/privacy — the same
// facts those pages state, in the landing page's shorter voice. No new claim
// originates here. These are also the questions the ask box below the list can
// answer from cache, so the two never disagree.
const FAQ: { q: string; a: string }[] = [
  {
    q: "Is it really free?",
    a: "Yes. The whole monorepo is MIT-licensed and readable without an account. We charge for integration work, not for the software, and there is no hosted tier or usage bill.",
  },
  {
    q: "Where does my provider key live?",
    a: "In the page's memory for the current tab, and nowhere else. The stack writes your provider and model choice to local storage and never persists the key; it is forwarded per request and gone when the tab closes.",
  },
  {
    q: "Do I have to run all nine modules?",
    a: "No. Each runs standalone or composes with the rest. The vector store and the LLM provider both sit behind interfaces, so taking one module and leaving the others is a supported path, not a fork.",
  },
  {
    q: "What is not built?",
    a: "Two modules are roadmap rather than shipped, there is no hosted product, and the broker adapters raise NotImplementedError — live trading is guarded by a human review gate, not a runtime interlock. The security page states every limit.",
  },
  {
    q: "Does it need NautilusTrader?",
    a: "Only for the quant work. Every backtest and optimise path runs through it, so digiquant depends on it; the rest of the stack does not.",
  },
];

export { FAQ };

export function FaqList() {
  return (
    <div className="grid gap-0">
      {FAQ.map((item) => (
        <details key={item.q} className="disclosure-row group border-b border-hair last:border-b-0">
          <summary className="flex items-center justify-between gap-[1rem] py-[1.1rem] font-mono text-[0.92rem] text-ink">
            {item.q}
            <span
              aria-hidden="true"
              className="shrink-0 font-mono text-ink-mute transition-transform duration-200 ease-brand group-open:rotate-45"
            >
              +
            </span>
          </summary>
          <p className="mt-0 mb-[1.2rem] max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.75] text-ink-soft">
            {item.a}
          </p>
        </details>
      ))}
    </div>
  );
}

// ═══ Voices ═════════════════════════════════════════════════════════════════

/**
 * The consolidated voice band (v15 point 5).
 *
 * The owner asked for the quotes to stop being two separate items — a band of
 * their own plus a line in the hero — and become one section. There are exactly
 * two voices and both are real:
 *
 * - the maintainer's, which is the statement the page has carried all along:
 *   the stack declines to bet on a provider, and where a claim cannot be counted
 *   it is written down as a limit rather than dressed up as a feature;
 * - DataTap's, quoted as *their* words about *their* integration — the
 *   documented self-hosted one. DataTap runs digichat on their own container
 *   host against their own Azure AI Foundry backend (see
 *   docs/architecture/digichat-self-hosted-release.md), and digithings does not
 *   host their instance. Their org links to its own public site.
 *
 * The voice doctrine is the primitive's contract and it holds here: real orgs
 * only, no invented orgs, no invented numbers. There is no `lockup` (the two
 * voices are not both about one product) and no `orgs` strip — a "trusted by"
 * row with a single real name would read as more than it is.
 */
const VOICES: TestimonialQuote[] = [
  {
    quote:
      "The stack declines to bet on a provider. Models, vector stores and execution venues sit behind interfaces, so the field can move faster than this architecture needs to. Where a claim can be counted it is counted and dated; where it cannot, it is written down as a limit instead of dressed up as a feature.",
    name: "Chris",
    role: "maintainer",
    org: "digithings",
  },
  {
    quote:
      "digichat gave our users a way to understand the product in their own words — and it runs on our own infrastructure, against our own backend, so the conversation never leaves the environment we already control.",
    name: "DataTap",
    role: "self-hosted digichat",
    org: "datatap.stream",
    href: "https://datatap.stream",
  },
];

export function Testimonials() {
  return <TestimonialWall columns={2} quotes={VOICES} className="w-full" />;
}

// ═══ Open source ════════════════════════════════════════════════════════════

/**
 * The open-source section (v13 → v15, #4429).
 *
 * The owner's direction: "show some insights on how it's open source and
 * highlight that it's an open source stack... the activity graph is interesting
 * there... reiterate the clone, git clone links to GitHub. And we could show a
 * few of the recent releases. Keep it at that. I think a more in-depth repo
 * view could be a separate page."
 *
 * So this is deliberately three plain things and nothing more: the six-month
 * contribution grid with its counted signals, the clone command as a single
 * copyable box, and the last few tagged releases. A fuller repo view lives at
 * /changelog, linked rather than reproduced. Every figure comes from the
 * committed snapshot or the shipped releases file — nothing is recomputed or
 * rounded here.
 *
 * Type scale is taken from the repo/changelog vocabulary rather than invented:
 * micro-caps labels use the page's `--type-meta` (0.75rem) via `GROUPED_LABEL`,
 * the clone command matches the primitives' mono meta scale (0.78rem, as
 * `.ra-clone code` does), and the prose is `--type-body`.
 */

// The last few tagged releases, straight from the shipped changelog data. The
// version keeps the redundant product prefix stripped so the row reads as
// `v2.3.1` next to its own `digichat` label, exactly as /changelog renders it.
const RECENT_RELEASES: ReleaseRailItem[] = (releases as {
  date: string;
  version: string;
  title: string;
  href: string;
  tag?: string;
  product: string;
}[]
)
  .slice(0, 4)
  .map((release) => ({
    product: release.product,
    version: release.version.replace(`${release.product} `, ""),
    date: release.date,
    title: release.title,
    href: release.href,
    tag: release.tag,
  }));

export function OpenSource() {
  return (
    <div className="grid gap-[2.4rem]">
      <RepoGrid />

      <div className="grid gap-[1.6rem] border-t border-hair pt-[2rem] min-[900px]:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="grid gap-[1.2rem]">
          <p className="m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            One MIT-licensed monorepo. Every module, test and CI definition is readable without an
            account — take it and run it yourself.
          </p>
          <div className="border border-hair bg-surface">
            <div
              className={`flex items-center justify-between px-[1rem] py-[0.5rem] ${GROUPED_LABEL}`}
            >
              <span>clone</span>
              <a
                className="text-ink-mute underline-offset-[3px] hover:text-ink hover:underline"
                href={REPO_URL}
                target="_blank"
                rel="noopener noreferrer"
              >
                github.com/digithings-ai
              </a>
            </div>
            <div className="border-t border-hair px-[1rem] py-[0.85rem] font-mono text-[0.78rem] text-ink">
              <span className="text-ink-mute">$ </span>
              {REPO_CLONE}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-[0.8rem]">
            <CtaLink href={REPO_URL} external>
              Browse the repository
            </CtaLink>
            <CtaLink href={CONTRIBUTING_URL} external variant="ghost">
              Contributing
            </CtaLink>
          </div>
        </div>

        <div className="min-w-0">
          <p className={`m-0 mb-[1.2rem] ${GROUPED_LABEL}`}>recent releases</p>
          <ReleaseRail items={RECENT_RELEASES} />
          <p className="mt-[1.6rem] mb-0 font-mono text-[0.75rem] text-ink-mute">
            <CtaLink href="/changelog" variant="ghost" className="text-[0.75rem]">
              All tagged releases
            </CtaLink>
          </p>
        </div>
      </div>
    </div>
  );
}
