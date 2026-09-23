import {
  MotionReveal,
  RepoActivity,
  TestimonialWall,
  type TestimonialQuote,
} from "@digithings/ui";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_URL, repoActivity } from "@/lib/repoActivity";

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

// The band is the kit's own detailed repo view (`RepoActivity variant="detailed"`).
// The owner asked for the shared component here rather than a hand-rolled grid,
// and it carries everything the hand-rolled version did and more: the 30-day
// velocity, the current backlog, the contribution grid, the latest release, the
// clone command with its copy button, and the merged-PR / open-issue ledgers.
// Its contribution grid shortens with the column instead of scrolling, so the
// band needs no window constant of its own.

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
 *
 * The quotes are set as quotes, in quotation marks, and the maintainer's is
 * motion text (`<MotionReveal/>`): the words deepen in order as the line rides
 * up the page, so the claim is spelled out rather than dropped in. DataTap's
 * stays plain — a customer's words about their own deployment should be
 * readable the instant they are on screen, not performed at the reader. Both
 * remain legible with no JS and under `prefers-reduced-motion`.
 */
const VOICES: TestimonialQuote[] = [
  {
    quote: (
      <MotionReveal
        text={
          "\u201CThe stack declines to bet on a provider. Models, vector stores and execution venues sit behind interfaces, so the field can move faster than this architecture needs to. Where a claim can be counted it is counted and dated; where it cannot, it is written down as a limit instead of dressed up as a feature.\u201D"
        }
      />
    ),
    name: "Chris",
    role: "maintainer",
    org: "digithings",
  },
  {
    quote:
      "\u201Cdigichat gave our users a way to understand the product in their own words — and it runs on our own infrastructure, against our own backend, so the conversation never leaves the environment we already control.\u201D",
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
 * The open-source section (v13 → v15, #4429; cut back in round 4).
 *
 * The owner's direction was "show some insights on how it's open source and
 * highlight that it's an open source stack... the activity graph is interesting
 * there... reiterate the clone, git clone links to GitHub. And we could show a
 * few of the recent releases. Keep it at that. I think a more in-depth repo
 * view could be a separate page."
 *
 * Round 4 removed the releases half. The kit's detailed repo view already
 * renders the clone command with its own copy button, the contributing and repo
 * links, the last-30-day counts, the current backlog and both ledgers, so the
 * hand-rolled block beside it was repeating the same band — and the "recent
 * releases" rail that came with it had a second answer to "what shipped last"
 * that had to be reconciled with the snapshot's own. One source, one answer, one
 * card. Every figure comes from the committed snapshot; nothing is recomputed or
 * rounded here.
 */

export function OpenSource() {
  return (
    /* The kit's component rather than a remix of it, at the full width of the
       band. `min-w-0` keeps the grid's max-content heat frame from setting the
       track's min-content and pushing the page sideways at narrow widths. */
    <RepoActivity
      variant="detailed"
      snapshot={repoActivity}
      repoUrl={REPO_URL}
      cloneCommand={REPO_CLONE}
      contributingUrl={CONTRIBUTING_URL}
      className="min-w-0"
    />
  );
}
