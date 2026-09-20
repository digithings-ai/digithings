import type { Metadata } from "next";
import {
  Figure,
  Mono,
  NumberedStages,
  OdometerStrip,
  PageHead,
  RuledList,
  RuledRow,
  type NumberedStage,
  type OdometerStat,
} from "@digithings/ui";
import { CtaLink } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import {
  CI_WORKFLOWS,
  COUNTED_AT,
  FRONTEND_TEST_FILES,
  PYTHON_TEST_FILES,
  TEST_LANES,
} from "@/lib/siteCounts";

export const metadata: Metadata = {
  title: "quality — the gates a change has to clear",
  description:
    "How change lands in digithings: per-component test lanes, a four-dimension scoring gate " +
    "(Security 8, Quality 8, Optimization 7, Accuracy 9), a frontend canon guard, and an honest " +
    "account of what the gate is and is not.",
};

// /quality — the engineering-process page, re-composed flat (D1, #4429).
//
// Every figure is single-sourced in lib/siteCounts.ts, where each snapshot
// carries the exact command that produced it and the date it was run — the page
// invites the reader to reproduce them, so a number that does not reproduce is
// worse than no number.
//
// The honest framing this page keeps: the four-dimension gate is TWO things, and
// conflating them would be a lie of omission.
//   1. scripts/score.py — a stdlib-only regex heuristic. It runs in CI as the
//      `score` job against the PR diff and exits non-zero below threshold, so it
//      really does block. Its own docstring says it is "NOT a full static
//      analyzer" and to "Treat results as a checklist aide, not a gate" — quoted
//      whole below.
//   2. docs/scoring/*.md — four ten-criterion rubrics the PR author self-scores
//      in the pull-request template. Judgement, recorded; not machine-checked.
// The individual rubric files' headers disagree with the thresholds score.py,
// docs/scoring/README.md and CLAUDE.md agree on; the page names that rather
// than papering over it, and cites the stricter reading.

const METRICS: OdometerStat[] = [
  { value: String(PYTHON_TEST_FILES), label: "python test files" },
  { value: String(FRONTEND_TEST_FILES), label: "frontend test files" },
  { value: String(CI_WORKFLOWS), label: "ci workflows" },
  { value: String(TEST_LANES), label: "test lanes" },
];

// The four dimensions, with the threshold as the tag.
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
      `${TEST_LANES} test workflows, most of them one per component, fired by a path filter so a ` +
      "change to digikey does not wait on the quant suite. Four are cross-cutting instead: " +
      "end-to-end, the scoring job, the isolated Nautilus run, and the research graph spec.",
  },
  {
    term: "An isolated Nautilus lane",
    body:
      "Tests that import NautilusTrader run in their own workflow and are ignored during ordinary " +
      "collection. The Rust engine initialises its logger once per process, so real-engine tests " +
      "cannot share a run with everything else — the isolation is a correctness requirement.",
  },
  {
    term: "Type checking",
    body:
      "A dedicated mypy workflow over the shared Python libraries — digibase and digikey — on " +
      "every pull request that touches them. The frontend apps have no type-check lane of their " +
      "own: they are type-checked by the production build, which CI runs as a deploy check.",
  },
  {
    term: "The frontend canon guard",
    body:
      "A script that scans every tracked frontend file for raw Tailwind palette utilities, " +
      "pre-canon class vocabulary and colour literals in component code, and ratchets on new " +
      "app-local CSS class families. Pages assemble from the shared design system rather than " +
      "growing private dress — this page was built under that constraint.",
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
      "Every change traces to a GitHub issue — a task branch carrying the issue number, or a " +
      "closing keyword in the pull request. Documentation and chore branches are deliberately " +
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
      "and it will miss a novel one. Its own docstring says so.",
  },
  {
    term: "Half the gate is self-assessed",
    body:
      "The forty rubric criteria are evaluated by the change's author in the pull-request " +
      "template. That is a design choice with a real failure mode: an author who scores generously " +
      "produces a green gate. Named human-review triggers exist because the self-score alone is " +
      "not sufficient.",
  },
  {
    term: "Frontend is scored differently",
    body:
      "The score job excludes apps/** and packages/** entirely: the rubrics are Python-oriented " +
      "and misfire on JS and CSS. Presentation work is gated instead by secret scanning, the canon " +
      "guard, lint, and a production build that fails on a type error. Only two of the front ends " +
      "run their test suites in CI; the marketing sites and the shared component package have no " +
      "CI test lane, so their tests are a local discipline — a narrower net, honestly narrower.",
  },
  {
    term: "Test count is not coverage",
    body:
      "The figures above count files, not lines exercised, and a file count says nothing about " +
      "assertion quality. The rubrics push at that directly, but a published coverage percentage " +
      "is not something this page claims.",
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
          human to look. Here is what that path checks — and, at the bottom, where it is weaker than
          it sounds.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// counted, not estimated"}</span>
            <Figure
              n={1}
              caption={`counted ${COUNTED_AT} · they grow · file counts, not coverage`}
              className="mt-[1.2rem]"
            >
              <OdometerStrip stats={METRICS} />
            </Figure>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <span className="kicker">{"// the scoring gate"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              Four rubrics live in <Mono>docs/scoring/</Mono>, ten criteria each, one point per
              criterion, no partial credit. A change is scored on all four and every one has to
              clear its own bar.
            </p>
            <NumberedStages stages={DIMENSIONS} className="mt-[2rem] max-w-[760px]" />
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// how the gate runs"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              <Mono>scripts/score.py</Mono> runs as a CI job against the pull request&rsquo;s diff and
              exits non-zero when any dimension is under threshold, so the check goes red and the
              merge waits. Its own header is blunter than that:{" "}
              <em>
                &ldquo;a heuristic scanner — it flags known anti-patterns by regex&hellip; It is NOT a
                full static analyzer. Treat results as a checklist aide, not a gate.&rdquo;
              </em>{" "}
              Both halves are true together: the script disclaims being a gate because a regex cannot
              judge a novel anti-pattern, and the workflow uses it as one anyway because a known
              anti-pattern should not need a reviewer to catch it.
            </p>
            <RuledList>
              <RuledRow term="The scanner">
                A blocking CI job. Regex over the diff, stdlib only. Catches known anti-patterns; it
                will miss a novel one.
              </RuledRow>
              <RuledRow term="The rubrics">
                Self-scored by the author in the pull-request template — forty criteria, recorded
                judgement, visible in the pull request and reviewable by whoever comes next.
              </RuledRow>
              <RuledRow term="Thresholds">
                Security 8, Quality 8, Optimization 7, Accuracy 9 — the figures the scanner&rsquo;s
                own table, the rubric index and the repository&rsquo;s contributor rules carry. The
                individual rubric files disagree, each header adding a second, lower number; the
                stricter reading is the one quoted here.
              </RuledRow>
            </RuledList>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <span className="kicker">{"// the lanes"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              {CI_WORKFLOWS} workflow files, most of them fired by path filters so a change pays only
              for the surface it touched.
            </p>
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
            <span className="kicker">{"// limits"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              A quality page that only lists gates is a marketing page. These are the four things
              worth knowing before you take the numbers above as a guarantee.
            </p>
            <RuledList>
              {LIMITS.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
            <p className="mt-[1.6rem] max-w-[64ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              The rubrics themselves are in the repository, so you can judge the bar rather than
              take our word for where it sits.{" "}
              <a className="text-accent [text-underline-offset:2px] hover:text-ink" href="/security">
                The security page
              </a>{" "}
              does the same for the runtime posture.
            </p>
            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="https://github.com/digithings-ai/digithings/tree/main/docs/scoring" external>
                Read the rubrics
              </CtaLink>
              <CtaLink href="/docs" variant="ghost">
                API reference
              </CtaLink>
            </div>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
