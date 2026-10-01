"use client";

import { useState } from "react";
import { type RepoContributor } from "@digithings/ui";
import { REPO_URL } from "@/lib/repoActivity";
import { OpenSourceLive } from "./OpenSourceLive";

/**
 * The open-source band and the FAQ (v12 → v15, #4429).
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
 * `Quotes` band is gone too, and the `Testimonials` reveal that replaced it was
 * removed entirely in round 6 ("i'd remove it remove the voices actually yeah").
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

// Answers are drawn from /security and /legal/privacy — the same
// facts those pages state, in the landing page's shorter voice. No new claim
// originates here. These are also the questions the ask box below the list can
// answer from cache, so the two never disagree.
const FAQ: { q: string; a: string }[] = [
  {
    q: "What does it cost?",
    a: "You don't pay for the software. It runs on your hardware, with your own provider key; model usage is billed by that provider. We charge for integration work only, with no hosted tier.",
  },
  {
    q: "Where does my provider key live?",
    a: "In the page's memory for the current tab, and nowhere else. The stack writes your provider and model choice to local storage and never persists the key; it is forwarded per request and gone when the tab closes.",
  },
  {
    q: "Do I have to run every module?",
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

/**
 * The FAQ list — an accordion, one answer open at a time.
 *
 * The owner's round-6 note: "those should follow the as in digi web we have faq
 * questions there only one should be opened at a time opening a second one
 * should close the previous one". The native `details` toggle is prevented and
 * the open row is held in state, so opening a second answer closes the first.
 * `group-open` still drives the `+` rotation because the `open` attribute is
 * controlled rather than absent.
 */
export function FaqList() {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="grid gap-0">
      {FAQ.map((item, i) => (
        <details
          key={item.q}
          open={open === i}
          className="disclosure-row group border-b border-hair last:border-b-0"
        >
          <summary
            onClick={(event) => {
              event.preventDefault();
              setOpen(open === i ? null : i);
            }}
            className="flex items-center justify-between gap-[1rem] py-[1.1rem] text-[0.95rem] text-ink"
          >
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
 * The maintainer, with the face from the site's own `public/team/chris.png`
 * (the owner: "we also need to add like the maintainer chris there's a profile
 * picture on the main digi things website you could take it there").
 */
const MAINTAINER: RepoContributor = {
  name: "Chris",
  role: "maintainer · digithings",
  avatarUrl: "/team/chris.png",
  url: REPO_URL,
};

export function OpenSource() {
  /* The kit's activity variant, at the full width of the band, rendered through
     the app's one client shell (#4429). `min-w-0` there keeps the grid's
     max-content heat frame from setting the track's min-content and pushing the
     page sideways at narrow widths. The per-module version rail was removed on
     the owner's request ("remove the // current versions section form the live
     repo status view"); the maintainer credit stays. */
  return <OpenSourceLive contributor={MAINTAINER} />;
}
