import type { Metadata } from "next";
import {
  CtaLink,
  DocumentFrame,
  Figure,
  GlyphList,
  GlyphRow,
  Mono,
  OdometerStrip,
  PageTitle,
  Prose,
  Section,
  type OdometerStat,
} from "@digithings/ui";
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

// /quality — the engineering-evidence page, rebuilt flat on the document
// grammar (D1, #4429). Four blocks and nothing else: the counted figures, the
// scoring gate (its four dimensions and how the scanner blocks on them), the
// test lanes, and the limits. No bands, no numbered spine, no second list
// grammar — the old "scoring gate" and "how the gate runs" sections merged
// because they describe one mechanism.
//
// The honest framing this page keeps: the four-dimension gate is TWO things,
// and conflating them would be a lie of omission.
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
//
// Every figure is single-sourced in lib/siteCounts.ts, where each snapshot
// carries the exact command that produced it and the date it was run — the page
// invites the reader to reproduce them, so a number that does not reproduce is
// worse than no number.

const METRICS: OdometerStat[] = [
  { value: String(PYTHON_TEST_FILES), label: "python test files" },
  { value: String(FRONTEND_TEST_FILES), label: "frontend test files" },
  { value: String(CI_WORKFLOWS), label: "ci workflows" },
  { value: String(TEST_LANES), label: "test lanes" },
];

// The four dimensions, with the threshold the scanner's own table carries.
const DIMENSIONS: { name: string; threshold: string; body: string }[] = [
  {
    name: "Security",
    threshold: "≥ 8 / 10",
    body:
      "No secrets in source. Pydantic validation at every HTTP, MCP and CLI boundary. Protected " +
      "routes scope-checked and fail-closed when auth is unconfigured. No new loopback exception, " +
      "no debug back door, and no live-trading path touched without a human gate.",
  },
  {
    name: "Quality",
    threshold: "≥ 8 / 10",
    body:
      "Pydantic v2 and Polars only — no pandas. Ruff clean at line length 100. A test for every " +
      "new public function or route. No file over 400 lines, no orphaned exports, structured " +
      "errors rather than bare raises, and the component's ARCHITECTURE.md updated in the same " +
      "change.",
  },
  {
    name: "Optimization",
    threshold: "≥ 7 / 10",
    body:
      "LLM calls routed through the cached LiteLLM path with no hardcoded model strings. Polars " +
      "lazy frames with a single collect. No N+1 request or embedding loops, no blocking call in " +
      "an async route, and the ten-million-row backtest budget held.",
  },
  {
    name: "Accuracy",
    threshold: "≥ 9 / 10",
    body:
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
      "A convention rather than a gate: a change is meant to trace to a GitHub issue — a task " +
      "branch carrying the issue number, or a closing keyword in the pull request. CI used to " +
      "check this and no longer does; the job was dropped in 2026-08 because it was never a " +
      "required check, so the trail is kept by habit and review rather than enforced.",
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
      "The score job scores a diff that excludes apps/** and packages/** by pathspec, so the rubrics never see JS or CSS — rightly, " +
      "since the heuristics are Python-oriented and misfire on them. Presentation work is gated instead by secret scanning, the canon " +
      "guard, lint, typecheck, and a production build that fails on a type error. Every frontend workspace's suite runs in a CI lane — digithings-web, digiquant-web, the dashboard, digichat, the shared ui packages, cron, and the Cloudflare workers each have one. " +
      "digiquant-web's pipeline-data pin, which holds the site's ten portfolio chips in order against the backend graph and pins the twenty-chip total, " +
      "is enforced on every change that touches the app or that graph.",
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
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle title="Gates, and what they miss.">
              Every change to this repository clears the same path: a per-component test lane, a
              four-dimension score against published rubrics, and a set of named triggers that force
              a human to look. Here is what that path checks — and where it is weaker than it
              sounds.
            </PageTitle>
          </div>

          <Section
            id="counted"
            title="Counted, not estimated"
            lede={`Every figure is a repository snapshot taken ${COUNTED_AT} on a clean checkout — file counts, not coverage.`}
          >
            <Figure
              n={1}
              caption={
                <>
                  Single-sourced in <Mono>lib/siteCounts.ts</Mono> — file counts, not coverage.
                </>
              }
            >
              <OdometerStrip stats={METRICS} />
            </Figure>
          </Section>

          <Section
            id="gate"
            title="The scoring gate"
            lede="Four rubrics live in docs/scoring/, ten criteria each, one point per criterion, no partial credit. A change is scored on all four and every one has to clear its own bar."
          >
            <GlyphList>
              {DIMENSIONS.map((dimension) => (
                <GlyphRow key={dimension.name} label={dimension.name}>
                  <Mono>{dimension.threshold}</Mono> — {dimension.body}
                </GlyphRow>
              ))}
            </GlyphList>

            <Prose className="mt-[1.6rem]">
              <p>
                <Mono>scripts/score.py</Mono> runs as a CI job against the pull request&rsquo;s diff
                and exits non-zero when any dimension is under threshold, so the check goes red and
                the merge waits. Its own header is blunter than that:{" "}
                <em>
                  &ldquo;a heuristic scanner — it flags known anti-patterns by regex&hellip; It is
                  NOT a full static analyzer. Treat results as a checklist aide, not a gate.&rdquo;
                </em>{" "}
                Both halves are true together: the script disclaims being a gate because a regex
                cannot judge a novel anti-pattern, and the workflow uses it as one anyway because a
                known anti-pattern should not need a reviewer to catch it.
              </p>
            </Prose>

            <GlyphList className="mt-[1.6rem]">
              <GlyphRow label="The scanner">
                A blocking CI job. Regex over the diff, stdlib only. Catches known anti-patterns; it
                will miss a novel one.
              </GlyphRow>
              <GlyphRow label="The rubrics">
                Self-scored by the author in the pull-request template — forty criteria, recorded
                judgement, visible in the pull request and reviewable by whoever comes next.
              </GlyphRow>
              <GlyphRow label="Thresholds">
                Security 8, Quality 8, Optimization 7, Accuracy 9 — the figures the
                scanner&rsquo;s own table, the rubric index and the repository&rsquo;s contributor
                rules carry. The individual rubric files disagree, each header adding a second,
                lower number; the stricter reading is the one quoted here.
              </GlyphRow>
            </GlyphList>
          </Section>

          <Section
            id="lanes"
            title="How a change is tested"
            lede={`${CI_WORKFLOWS} workflow files, most of them fired by path filters so a change pays only for the surface it touched.`}
          >
            <GlyphList>
              {LANES.map((lane) => (
                <GlyphRow key={lane.term} label={lane.term}>
                  {lane.body}
                </GlyphRow>
              ))}
            </GlyphList>
          </Section>

          <Section
            id="limits"
            title="What this does not prove"
            lede="A quality page that only lists gates is a marketing page. These are the four things worth knowing before you take the numbers above as a guarantee."
          >
            <GlyphList>
              {LIMITS.map((limit) => (
                <GlyphRow key={limit.term} label={limit.term}>
                  {limit.body}
                </GlyphRow>
              ))}
            </GlyphList>

            <Prose className="mt-[1.6rem]">
              <p>
                The rubrics themselves are in the repository, so you can judge the bar rather than
                take our word for where it sits. <a href="/security">The security page</a> does the
                same for the runtime posture.
              </p>
            </Prose>

            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink
                href="https://github.com/digithings-ai/digithings/tree/main/docs/scoring"
                external
              >
                Read the rubrics
              </CtaLink>
            </div>
          </Section>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
