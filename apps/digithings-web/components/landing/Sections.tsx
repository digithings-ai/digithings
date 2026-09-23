import {
  RepoActivity,
  WordReveal,
  modules,
  type RepoContributor,
  type RepoModuleRelease,
} from "@digithings/ui";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_URL, repoActivity } from "@/lib/repoActivity";
import { moduleVersion } from "@/lib/moduleCounts";
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
 * `Quotes` band is gone too: it is now `Testimonials`, a standalone pull-quote
 * per voice revealed with the kit's `<WordReveal/>` (v15 point 5; reveal in v16).
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
    a: "Two modules are roadmap rather than shipped, there is no hosted product, and the broker adapters raise NotImplementedError — live trading is guarded by a human review gate, not a runtime interlock. The security page lists the known limits.",
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
 * The voices band, revealed as standalone quotes (v15 → v16, #4429).
 *
 * The owner's ask, verbatim: "the quotes i want to show like we have in the
 * typography page ... this word reveal animation i think that's what i'd want
 * ... essentially revealing the quotes as you scroll down but there shouldn't
 * be a box around them they should appear as standalone quotes of their own".
 *
 * So the boxed `TestimonialWall` presentation is gone. Each voice is a
 * `<WordReveal/>` — the kit's pinned-blur reveal, the exact one the typography
 * reference renders — whose words fill from blur as the line rides up the
 * viewport. There is no border, card or surface: a pull-quote is the words and
 * their attribution, nothing else. The quotation marks are the frame now, so
 * the marks stay (U+201C/U+201D) and the wording is unchanged.
 *
 * ## The pinning trade-off (recorded, because this file argues about it)
 *
 * `WordReveal` pins a 150vh track per call, and this band holds two quotes, so
 * it adds ~300vh of pinned scroll. That is a real cost, and this file's other
 * docblocks — `Boot` above, and the Colophon note in app/page.tsx — argue
 * against exactly this kind of dead scroll. The owner asked for the reveal
 * anyway, so the only open question is how to spend it:
 *
 * - Two adjacent tracks (what is built). Each quote owns its own reveal and the
 *   reader meets them one at a time, which is the voice doctrine this band has
 *   carried all along — "the reader meets them one at a time instead of
 *   comparing them side by side". Composed by mapping `<WordReveal/>` over the
 *   two voices; no new primitive.
 * - One shared track. `WordReveal` takes a single `text` string, so putting both
 *   quotes on one pinned track means either a new primitive or a fork of the
 *   kit's scroll mapping, and the task ruled that out. It would save ~150vh but
 *   buy it with a primitive the kit does not have — the wrong trade.
 *
 * The 150vh track is also what lets the reveal finish by mid-viewport and never
 * scroll away half-read, and `word-reveal.css` collapses it to a static,
 * fully-legible block under `prefers-reduced-motion` and under `html.no-js`, so
 * the quotes are never gated behind the animation.
 *
 * Both voices are real:
 *
 * - the maintainer's, the statement the page has carried all along: the stack
 *   declines to bet on a provider, and where a claim cannot be counted it is
 *   written down as a limit rather than dressed up as a feature;
 * - DataTap's, quoted as *their* words about *their* integration — the
 *   documented self-hosted one. DataTap runs digichat on their own container
 *   host against their own Azure AI Foundry backend (see
 *   docs/architecture/digichat-self-hosted-release.md), and digithings does not
 *   host their instance. Their org links to its own public site.
 *
 * The voice doctrine is the data's contract and it holds here: real orgs only,
 * no invented orgs, no invented numbers.
 */
type Voice = {
  /** The quote, typographic marks included (U+201C/U+201D). Revealed word by word. */
  text: string;
  name: string;
  role: string;
  org: string;
  /** Public site for the org, when it has one. */
  href?: string;
};

const VOICES: Voice[] = [
  {
    text: "\u201CThe stack declines to bet on a provider. Models, vector stores and execution venues sit behind interfaces, so the field can move without the architecture having to. Where a claim can be counted it is counted and dated; where it cannot, it is written down as a limit instead of dressed up as a feature.\u201D",
    name: "Chris",
    role: "maintainer",
    org: "digithings",
  },
  {
    text: "\u201Cdigichat gave our users a way to understand the product in their own words — and it runs on our own infrastructure, against our own backend, so the conversation never leaves the environment we already control.\u201D",
    name: "DataTap",
    role: "self-hosted digichat",
    org: "datatap.stream",
    href: "https://datatap.stream",
  },
];

export function Testimonials() {
  return (
    /* Two tracks, one per voice, in document order — the reader meets the
       maintainer's claim, then DataTap's. The `<figure>` is semantics only:
       `m-0`, no border, no background, so nothing draws a box around the
       quote. The attribution is a sibling of the track, so it reads beneath the
       quote once the pinned hold releases. */
    <div className="flex flex-col">
      {VOICES.map((voice) => (
        <figure key={voice.name} className="m-0">
          <blockquote className="m-0">
            <WordReveal text={voice.text} />
          </blockquote>
          <figcaption className={`mt-[0.9rem] ${GROUPED_LABEL}`}>
            {voice.name} · {voice.role} ·{" "}
            {voice.href ? (
              <a
                className="underline-offset-[3px] hover:text-ink hover:underline"
                href={voice.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                {voice.org}
              </a>
            ) : (
              voice.org
            )}
          </figcaption>
        </figure>
      ))}
    </div>
  );
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

/**
 * The current version of every shipped module — the activity variant's ledger.
 *
 * The owner's round-5 note: "the latest releases for every module we should have
 * the latest versions for every module not just digi chat". The changelog can't
 * answer that — release-please only cuts releases for digichat and digiskills, so
 * a ledger built from `releases.json` listed two modules and silently dropped the
 * other seven. The version each module declares for itself is the fact that does
 * cover every one, so it comes from the generated `module-counts.json`
 * (`moduleVersion`), walked in the same `graphOrder` the mosaic uses.
 *
 * Roadmap modules (digistore, digilink) declare no version and are absent, not
 * shown as `0.0.0`. No `url` is set: there is no per-module release page to point
 * at, and the band's own "browse the repo" link already goes to GitHub.
 */
const MODULE_RELEASES: RepoModuleRelease[] = [...modules]
  .sort((a, b) => a.graphOrder - b.graphOrder)
  .flatMap((m) => {
    const version = moduleVersion(m.id);
    return version ? [{ name: m.id, version }] : [];
  });

/**
 * The maintainer. No `avatarUrl` is set: the kit falls back to a monogram, and
 * inventing an avatar URL would be a guess. Supply the GitHub handle (or a
 * hosted image) to show the face.
 */
const MAINTAINER: RepoContributor = {
  name: "Chris",
  role: "maintainer · digithings",
  url: REPO_URL,
};

export function OpenSource() {
  return (
    /* The kit's component rather than a remix of it, at the full width of the
       band. `min-w-0` keeps the grid's max-content heat frame from setting the
       track's min-content and pushing the page sideways at narrow widths.
       The activity variant is the middle ground the owner asked for: the summary
       metrics and the contribution graph are kept, the two ledgers are dropped,
       and the version ledger and the maintainer take their place. */
    <RepoActivity
      variant="activity"
      snapshot={repoActivity}
      repoUrl={REPO_URL}
      cloneCommand={REPO_CLONE}
      contributingUrl={CONTRIBUTING_URL}
      moduleReleases={MODULE_RELEASES}
      contributor={MAINTAINER}
      className="min-w-0"
    />
  );
}
