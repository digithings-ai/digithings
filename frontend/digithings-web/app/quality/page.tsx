import type { Metadata } from "next";
import Link from "next/link";
import {
  NumberedStages,
  OdometerStrip,
  Reveal,
  type NumberedStage,
  type OdometerStat,
} from "@digithings/web";
import { DtFooter } from "@/components/DtFooter";
import { Mono, PageHead, RuledList, RuledRow } from "../_company/prose";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "quality — the gates a change has to clear",
  description:
    "How change lands in digithings: per-component test lanes, a four-dimension scoring gate " +
    "(Security 8, Quality 8, Optimization 7, Accuracy 9), a frontend canon guard, and an honest " +
    "account of what the gate is and is not.",
};

// /quality — the engineering-process page, written from the repository.
//
// COUNTS ARE A SNAPSHOT. Every figure in COUNTED_AT / METRICS below was counted
// on the date named, at the commit this page was written against, with the
// commands recorded next to each entry. They drift as the repo grows, so they
// are collected here in one block: refreshing the page is one edit, and the
// date is rendered on the page so a stale number reads as dated rather than
// as a false claim.
//
// The honest framing this page has to keep: the four-dimension gate is TWO
// things, and conflating them would be a lie of omission.
//   1. scripts/score.py — a stdlib-only regex heuristic. It runs in CI as the
//      `score` job against the PR diff and exits non-zero below threshold, so
//      it really does block. Its own docstring (scripts/score.py:14-15) says it
//      is "NOT a full static analyzer" and to "Treat results as a checklist
//      aide, not a gate" — quote that clause WHOLE. Lifting the first half while
//      asserting the script blocks is exactly the selective move this page
//      spends four paragraphs claiming not to make, so the page prints the
//      disclaimer verbatim and then reconciles it against the workflow.
//   2. docs/scoring/*.md — four ten-criterion rubrics the PR author self-scores
//      in the pull-request template. Judgement, recorded; not machine-checked.
// frontend/** is excluded from the score job (the rubrics are Python-oriented
// and misfire on JS/CSS), as are the hook scripts that DEFINE the live-trading
// detection regex and would otherwise self-match.
//
// Note also: the rubric files' own headers say "< 7 blocks merge" (SECURITY,
// QUALITY), "< 8" (ACCURACY), "< 6" (OPTIMIZATION), while docs/scoring/README.md
// and score.py's THRESHOLDS dict block below the target itself. The page links
// docs/scoring/, so a reader who follows the link meets that disagreement — it
// is therefore NAMED on the page rather than quietly omitted, and the page cites
// the stricter 8 / 8 / 7 / 9 that score.py, the README and CLAUDE.md agree on.
// The doc fix belongs in a docs change; do not silently paper over it here.

const COUNTED_AT = "5 August 2026";

// Every figure below is the output of the command above it, run on a clean
// checkout of develop. Re-run them when you touch this block: the page invites
// the reader to, so a number that does not reproduce is worse than no number.
// (The python count read 319 here until 2026-08-05 while the command returned
// 321 — it never reproduced, including at the commit it was written on.)
//
// find tests -name 'test_*.py' | wc -l                                  → 321
// find frontend -path '*/node_modules' -prune -o \( -name '*.test.ts*'
//   -o -name '*.spec.ts*' -o -name '*.test.js' -o -name '*.test.mjs' \) -print  → 180
//   ^ the -print is load-bearing: without it find's implicit print also emits the
//     pruned node_modules directories, and the command returns 186 instead.
// ls .github/workflows/ | grep -c '\.yml$'                              → 63
// ls .github/workflows/ | grep -c '^test-'                              → 17
const METRICS: OdometerStat[] = [
  { value: "321", label: "python test files" },
  { value: "180", label: "frontend test files" },
  { value: "63", label: "ci workflows" },
  { value: "17", label: "test lanes" },
];

// The four dimensions, with the threshold as the tag. Each `mech` names what
// the dimension actually looks for, drawn from that rubric's criteria table.
const DIMENSIONS: NumberedStage[] = [
  {
    num: "01",
    tag: "≥ 8 / 10",
    title: "Security",
    mech:
      "No secrets in source. Pydantic validation at every HTTP, MCP and CLI boundary. Protected " +
      "routes scope-checked and fail-closed when auth is unconfigured. No new loopback exception, " +
      "no debug back door, and no live-trading path touched without a human gate.",
  },
  {
    num: "02",
    tag: "≥ 8 / 10",
    title: "Quality",
    mech:
      "Pydantic v2 and Polars only — no pandas. Ruff clean at line length 100. A test for every " +
      "new public function or route. No file over 400 lines, no orphaned exports, structured " +
      "errors rather than bare raises, and the component's ARCHITECTURE.md updated in the same " +
      "change.",
  },
  {
    num: "03",
    tag: "≥ 7 / 10",
    title: "Optimization",
    mech:
      "LLM calls routed through the cached LiteLLM path with no hardcoded model strings. Polars " +
      "lazy frames with a single collect. No N+1 request or embedding loops, no blocking call in " +
      "an async route, and the ten-million-row backtest budget held.",
  },
  {
    num: "04",
    tag: "≥ 9 / 10",
    title: "Accuracy",
    mech:
      "The strictest threshold, because this is the dimension about being wrong rather than being " +
      "untidy: correct LangGraph state transitions, an audit event for every persistent state " +
      "change, no silenced error paths, unchanged public API contracts, preserved Nautilus event " +
      "lifecycle, and assertions that check values rather than merely not throwing.",
  },
];

// What runs on a pull request, and what each lane refuses to let through.
const LANES: { term: string; body: string }[] = [
  {
    term: "Per-component test lanes",
    body:
      "Seventeen test workflows, most of them one per component, fired by a path filter so a change " +
      "to digikey does not wait on the quant suite. Four of the seventeen are cross-cutting instead: " +
      "end-to-end, the scoring job, the isolated Nautilus run, and the research graph spec. Adding a " +
      "component means wiring its lane; the filter is explicit rather than inferred.",
  },
  {
    term: "An isolated Nautilus lane",
    body:
      "Tests that import NautilusTrader run in their own workflow and are ignored during ordinary " +
      "collection. The Rust engine initialises its logger once per process, so real-engine tests " +
      "cannot share a run with everything else — the isolation is a correctness requirement, not " +
      "a preference.",
  },
  {
    term: "Type checking",
    body:
      "A dedicated mypy workflow over the shared Python libraries — digibase and digikey — on every " +
      "pull request that touches them. The frontend apps have no type-check lane of their own: they " +
      "are type-checked by the production build, which CI runs as a deploy check on any pull request " +
      "touching an app or the shared design packages, and which fails on a type error. Strict typing " +
      "is a rubric criterion too, so an untyped signature also costs a score point.",
  },
  {
    term: "The frontend canon guard",
    body:
      "A script that scans every tracked frontend file for raw Tailwind palette utilities, " +
      "pre-canon class vocabulary and colour literals in component code, and ratchets on new " +
      "app-local CSS class families. Pages have to assemble from the shared design system rather " +
      "than growing private dress — this page was built under that constraint.",
  },
  {
    term: "Documentation link checking",
    body:
      "Internal markdown links are validated in CI, and the architecture documents are synced. A " +
      "dead cross-reference in an ARCHITECTURE.md fails the same way a dead import would.",
  },
  {
    term: "Workflow and compose linting",
    body:
      "actionlint over the workflow files and a compose validation job, so the CI definition and " +
      "the deployment topology are themselves checked rather than trusted.",
  },
  {
    term: "Pull-request hygiene",
    body:
      "Every change has to trace to a GitHub issue — a task branch carrying the issue number, or " +
      "a closing keyword in the pull request. Documentation and chore branches are deliberately " +
      "exempt, so the rule stays enforceable instead of routinely waived.",
  },
];

// The part that makes the rest believable.
const LIMITS: { term: string; body: string }[] = [
  {
    term: "The scanner is a heuristic",
    body:
      "The scoring script is regular expressions over a diff, standard library only. It catches " +
      "known anti-patterns — a pandas import, a bare exec, a blocking sleep in an async handler — " +
      "and it will miss a novel one. Its own docstring says so, and this page is not going to say " +
      "otherwise.",
  },
  {
    term: "Half the gate is self-assessed",
    body:
      "The forty rubric criteria are evaluated by the change's author in the pull-request " +
      "template. That is a design choice with a real failure mode: an author who scores " +
      "generously produces a green gate. Named human-review triggers — auth and crypto changes, " +
      "broker or live-trading paths, a score below threshold twice, a new external dependency, " +
      "novel architecture — exist because the self-score alone is not sufficient.",
  },
  {
    term: "Frontend is scored differently",
    body:
      "The score job excludes frontend/** entirely: the rubrics are Python-oriented and misfire on " +
      "JS and CSS. Presentation work is gated instead by secret scanning, the canon guard, lint, and " +
      "a production build that fails on a type error. Only two of the front ends — the chat UI and " +
      "the digiquant dashboard — run their test suites in CI; the marketing sites and the shared " +
      "component package have no CI test lane, so their tests are a local discipline. A narrower " +
      "net, honestly narrower.",
  },
  {
    term: "Test count is not coverage",
    body:
      "The figures above count files, not lines exercised, and a file count says nothing about " +
      "assertion quality. The rubrics push at that directly — meaningful assertions, no test " +
      "deleted or weakened to go green — but a published coverage percentage is not something " +
      "this page claims.",
  },
];

export default function QualityPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <PageHead
          kicker={"// quality"}
          title={
            <>
              Gates, <em>and what they miss.</em>
            </>
          }
        >
          Every change to this repository clears the same path: a per-component test lane, a
          four-dimension score against published rubrics, and a set of named triggers that force a
          human to look. Here is what that path actually checks — and, at the bottom, where it is
          weaker than it sounds.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// counted, not estimated"}</span>
              <h2>Four figures from the repository.</h2>
              <p>
                Counted from the tree with the commands recorded in this page&rsquo;s source, so
                anyone can reproduce them.
              </p>
            </Reveal>
            <Reveal>
              <OdometerStrip stats={METRICS} className="mx-auto max-w-[880px]" />
            </Reveal>
            <p className="mx-auto mt-[1.1rem] max-w-[880px] text-center font-mono text-[0.72rem] text-ink-mute">
              counted {COUNTED_AT} · they grow · file counts, not coverage
            </p>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// the scoring gate"}</span>
              <h2>Four dimensions, four thresholds.</h2>
              <p>
                Four rubrics live in <Mono>docs/scoring/</Mono>, ten criteria each, one point per
                criterion, no partial credit. A change is scored on all four and every one has to
                clear its own bar.
              </p>
            </Reveal>
            <NumberedStages stages={DIMENSIONS} className="max-w-[760px]" />
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// how the gate runs"}</span>
              <h2>One half is machine-checked. Say which.</h2>
            </Reveal>
            <div className="grid gap-[1.1rem] md:grid-cols-2">
              <Reveal className="mod-card">
                <div className="mod-card-top">
                  <h3>The scanner</h3>
                  <span className="dg-tier t-core">blocking</span>
                </div>
                <p className="text-[0.92rem] leading-[1.65] text-ink-soft">
                  {/* Explicit {" "}: when <Mono> is the FIRST child of the
                      paragraph, the SWC JSX transform drops the space that
                      follows the closing tag (verified in the exported HTML —
                      it rendered "score.pyruns"). Every other Mono on these
                      pages has a real text or expression child before it and
                      keeps its space; this one needs the separator spelled out. */}
                  <Mono>scripts/score.py</Mono>{" "}
                  runs as a CI job against the pull request&rsquo;s
                  diff and exits non-zero when any dimension is under threshold, so the check goes
                  red and the merge waits. Its own header is blunter than that:{" "}
                  <em>
                    &ldquo;a heuristic scanner — it flags known anti-patterns by regex&hellip; It is
                    NOT a full static analyzer. Treat results as a checklist aide, not a gate.&rdquo;
                  </em>{" "}
                  Both halves are true and worth stating together: the script disclaims being a gate
                  because a regex cannot judge a novel anti-pattern, and the workflow uses it as one
                  anyway because a known anti-pattern should not need a reviewer to catch it.
                </p>
              </Reveal>
              <Reveal className="mod-card">
                <div className="mod-card-top">
                  <h3>The rubrics</h3>
                  <span className="dg-tier">self-scored</span>
                </div>
                <p className="text-[0.92rem] leading-[1.65] text-ink-soft">
                  The forty criteria are worked through by the author in the pull-request template:
                  check what you pass, write a note for what you do not and why it is acceptable,
                  leave anything you are unsure about unchecked. Recorded judgement, visible in the
                  pull request, reviewable by whoever comes next.
                </p>
              </Reveal>
            </div>
            <p className="mt-[1.8rem] max-w-[64ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              Thresholds are Security 8, Quality 8, Optimization 7, Accuracy 9 — the figures the
              scanner&rsquo;s own table, the rubric index and the repository&rsquo;s contributor rules
              all carry. The individual rubric files disagree: each one&rsquo;s header adds a second,
              lower number below which merge is blocked. That contradiction is in the repository, not
              resolved by this page, and the stricter reading is the one quoted here.
            </p>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// the lanes"}</span>
              <h2>What runs before a merge.</h2>
              <p>
                Sixty-three workflow files, most of them fired by path filters so a change pays only
                for the surface it touched.
              </p>
            </Reveal>
            <RuledList>
              {LANES.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// limits"}</span>
              <h2>Where this is weaker than it sounds.</h2>
              <p>
                A quality page that only lists gates is a marketing page. These are the four things
                worth knowing before you take the numbers above as a guarantee.
              </p>
            </Reveal>
            <RuledList>
              {LIMITS.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
            <p className="mt-[1.8rem] max-w-[64ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              The rubrics themselves are in the repository, so you can judge the bar rather than
              take our word for where it sits.{" "}
              <Link className="text-accent [text-underline-offset:2px] hover:text-ink" href="/security">
                The security page
              </Link>{" "}
              does the same for the runtime posture.
            </p>
            <div className="mt-[2rem] flex flex-wrap gap-[0.8rem]">
              <a
                className="btn btn-primary"
                href="https://github.com/digithings-ai/digithings/tree/main/docs/scoring"
                target="_blank"
                rel="noopener noreferrer"
              >
                Read the rubrics <span aria-hidden="true">→</span>
              </a>
              <Link className="btn btn-ghost" href="/docs">
                API reference
              </Link>
            </div>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
