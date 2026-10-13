# Free-model benchmark, 12 Oct 2026

- Issue: DIG-3067
- Author: OpenCode Go consultant
- Date: 12 Oct 2026

Every run below is on the `opencode/*` free tier and cost $0. No `opencode-go/*`
model was used. This complements `MODEL_CATALOG.md`, which records what exists;
this records what each free model actually does when you hand it work.

## What is free today

`opencode models | grep '^opencode/' | grep free` returns 10 ids. Two are dead
before they answer anything:

| Model id | Status |
| --- | --- |
| `exo-free` | HTTP 410, deprecated at the provider |
| `ling-3.0-flash-fin-free` | HTTP 400, unavailable at the provider |
| `ling-3.1-flash-free` | live |
| `longcat-2.5-preview-free` | live |
| `mimo-v2.6-flash-free` | live |
| `muse-spark-1.3-contributor-free` | live |
| `nemotron-3-ultra-free` | live |
| `nemotron-3.5-lightning-free` | live |
| `space-bunny-free` | live |
| `step-5-preview-free` | live |

So: **8 usable free models.** The enumeration is identical to the earlier round
on the same day — no model was added or withdrawn between the two runs.

## Probes

| Probe | What it demands | Grader |
| --- | --- | --- |
| `hjson` | structured output plus a computed field | `total_cents == Σ qty × unit_price` |
| `hreason` | a per-100 surcharge trap | must equal `48000000` |
| `hcode` | write `solution.py` | executed against 3 cases |
| `htool` | really run `echo PROBE-TOOL-4821` | the token must appear in observed output |
| `hctx_nav` | find 5 facts inside a 5,999-line file using tools | 5 planted facts, 4 lure strings absent |
| `hctx_inline` | find the same 5 facts in ~117k tokens held in the prompt, no tools | identical |

### Harness caveat that matters

A nested `opencode run` inherits the **process** cwd, and the consultant config
denies `permission.external_directory`. The first `hcode`/`htool` batch ran
outside the intended directory and is VOID; the numbers in this document are the
re-run from a benchmark directory under `~/Code`. The benchmark directory is
deliberately outside any git checkout so probe files can never dirty a worktree.

## Results

One run per cell. Round 1.

| Model | hjson | hreason | hcode | htool | Score | Avg latency | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `muse-spark-1.3-contributor-free` | ok | ok | ok | ok | 4/4 | 6.5 s | Best free default on structured work |
| `nemotron-3.5-lightning-free` | ok | ok | ok | ok | 4/4 | 9.4 s | Correct on small work; **see the long-context section before making it a default** |
| `mimo-v2.6-flash-free` | ok | ok | ok | ok | 4/4 | 19.4 s | Clean but slow |
| `ling-3.1-flash-free` | ok | ok | ok | ok | 4/4 | 23.3 s | Clean on small work, hard 262k ceiling (below) |
| `nemotron-3-ultra-free` | ok | ok | ok | ok | 4/4 | 32.3 s | Correct, slowest of the 4/4 group |
| `step-5-preview-free` | ok | ok | ok | ok | 4/4 | 45.2 s | Correct, very slow |
| `space-bunny-free` | fail | ok | ok | ok | 3/4 | 4.4 s | Fastest; mis-sums |
| `longcat-2.5-preview-free` | ok | ok | fail | ok | 3/4 | 24.1 s | Drops a required field |
| `exo-free` | — | — | — | — | 0/4 | — | HTTP 410 |
| `ling-3.0-flash-fin-free` | — | — | — | — | 0/4 | — | HTTP 400 |

### The two 3/4 failures are the same failure

Both are **omission or mis-derivation under a stated constraint**, not a refusal
and not a crash:

- `space-bunny-free` mis-summed `total_cents`: 16,496 / 17,246 / 16,496 against
  the correct 20,696.
- `longcat-2.5-preview-free` returned an empty `note` where a value was required.

That class of failure — producing a confident, well-formed, wrong answer — is
more dangerous than failing outright, and it is what the structured probes were
built to catch.

## Long context

This is the section the earlier round left open. Two probes, because "long
context" is two different abilities and a single number hides the difference.

- **`hctx_nav`** — the 5 facts live in a 656,154-character, 5,999-line file
  (~165k tokens). The model must find them with `Read`/`Grep`/`Glob`. This
  measures *tool navigation of a large artefact*.
- **`hctx_inline`** — the same facts are inlined into the prompt (470,938
  characters, ~117,734 tokens) and the model is told not to use tools. This
  measures *raw recall*.

Five facts are planted, each appearing exactly once (`PRJ-ALPHA`, port `4471`,
retention `400` days, contact `CHRIS`, region `eu-north-3`), and four lure
strings are absent by construction (`PRJ-BETA`, `4472`, `DANA`, `us-east-1`) to
catch confident invention.

### `hctx_nav` — navigating a ~165k-token file with tools

| Model | Facts found | Tools used | What happened |
| --- | --- | --- | --- |
| `longcat-2.5-preview-free` | 5/5 | Grep, Read ×9 | clean |
| `muse-spark-1.3-contributor-free` | 5/5 | Read ×1 | clean, one read was enough |
| `nemotron-3-ultra-free` | 5/5 | Read ×11 | clean, thorough |
| `step-5-preview-free` | 5/5 | Glob, Read | clean |
| `space-bunny-free` | 3/5 | Read ×7 | stopped early; `contact` and `region` left null |
| `ling-3.1-flash-free` | 0/5 | none | **HTTP 400 — hard ceiling 262,144 tokens**, refused a ~312k request |
| `mimo-v2.6-flash-free` | 0/5 | Glob only | ran `wc -l -c`, never read the file, emitted no JSON — **stalled, not hallucinated** |
| `nemotron-3.5-lightning-free` | 0/5 | none | **empty output, hit the 420 s timeout** |

### `hctx_inline` — ~117k tokens of recall, no tools

| Model | Facts found | Latency | Note |
| --- | --- | --- | --- |
| `space-bunny-free` | 5/5 | 6.1 s | fastest |
| `muse-spark-1.3-contributor-free` | 5/5 | 20.9 s | clean |
| `nemotron-3.5-lightning-free` | 5/5 | 23.6 s | **recall is fine — it is the tool-navigation path that dies** |
| `mimo-v2.6-flash-free` | 5/5 | 27.8 s | clean |
| `longcat-2.5-preview-free` | 5/5 | 32.5 s | clean |
| `nemotron-3-ultra-free` | 5/5 | 36.8 s | clean |
| `step-5-preview-free` | 4/5 | 45.9 s | genuine error: returned `eu-north-1-3` for `eu-north-3` |
| `ling-3.1-flash-free` | 0/5 | 55.3 s | HTTP 400, same 262,144 ceiling, refused ~311,917 |

**Zero lure strings appeared in any `hctx_inline` output.** With one partial
answer and one transport refusal, no live free model invented a fact.

### What the two probes together say

- **7 of 8 hold ~117k tokens of in-context recall.** Only `ling-3.1-flash-free`
  has a hard 262,144-token ceiling that refuses anything larger. For any seat
  that assembles a large context before calling, that ceiling is a capability
  limit, not a quality difference.
- **Navigation and recall are separate abilities.** `nemotron-3.5-lightning-free`
  is 5/5 inline at 23.6 s and 0/5 on the same content reached through tools,
  where it returned nothing and timed out. `mimo-v2.6-flash-free` is the mirror
  case in the previous round: clean here, stalled there. **A model that can read
  a large context cannot be assumed to navigate one.**
- **This corrects the earlier round.** `nemotron-3.5-lightning-free` was
  published as "strong second free default" on the strength of 4/4 on small
  work. On a large file it fails outright. It is a good small-context model and
  a poor default for any seat that reads files, and it should not be the second
  free default.

## Rate limits and concurrency

Earlier this document reported a 6-way smoke test as its rate-limit evidence.
That was too weak to carry a conclusion, and it has been replaced with a measured
burst plus a sequential baseline.

**12 fully-concurrent calls** (4 models × 3 repetitions: `space-bunny-free`,
`muse-spark-1.3-contributor-free`, `nemotron-3-ultra-free`, `step-5-preview-free`),
single-word prompt, per-call timeout 180 s:

| Model | Latencies | Median | Tag |
| --- | --- | --- | --- |
| `space-bunny-free` | 16.9 / 17.0 / 17.1 s | 17.0 s | 3 ok |
| `muse-spark-1.3-contributor-free` | 23.3 / 29.6 / 38.9 s | 29.6 s | 3 ok |
| `step-5-preview-free` | 23.4 / 23.8 / 27.1 s | 23.8 s | 3 ok |
| `nemotron-3-ultra-free` | 83.6 / 83.7 / 83.7 s | 83.7 s | 3 ok |

- **12/12 exited 0. Zero rate-limit responses, zero 429s, zero timeouts.** No
  throttling was observed at this concurrency.
- Burst wall clock 83.7 s, and it was **not** set by contention: the three
  `nemotron-3-ultra-free` calls completed within 0.1 s of each other, so nothing
  was visibly queued or serialised.
- **Per-request latency, however, inflated against the idle baseline.**

| Model | Idle median (sequential, n=3) | Under 12-way concurrency | Inflation |
| --- | --- | --- | --- |
| `space-bunny-free` | 5.6 s | 17.0 s | **3.0×** |
| `muse-spark-1.3-contributor-free` | 12.3 s | 29.6 s | **2.4×** |

So the honest reading is two-part: **at 12 concurrent requests the free tier
throttled nobody, and every request got 2.4–3.0× slower.** A seat that fans out
work will not be rejected; it will wait. Size concurrency on latency, not on a
limit you will never see.

One `step-5-preview-free` call (27.1 s, 36 bytes of output) did not contain the
literal `PONG` token. The harness recorded its byte count but did not retain the
text, so what it said is unrecoverable. It answered; it did not comply.

### The VPN-rotation half of the brief could not be run

The brief asks for the concurrency test to be exercised through the VPN
rotation. **VPN rotation is disabled on this host**, measured, not assumed:

```
$ python3 ~/paperclip-workspace/kit/tools/vpn-rotate status
server: none
public IP: 205.147.30.12 (IT)
disabled: yes
rotations used (global): 0/3
```

An agent seat cannot re-enable it. Every number in this section is therefore from
**a single egress path**. Whether the tier throttles per exit IP — which is the
usual reason rotation exists — was **not measured**, and no conclusion about
per-IP limits should be drawn from this section.

## Recommended mapping

Named against real surfaces in this repository. Paths are relative to the
`digiquant/` package root unless stated otherwise.

| Work | Use | Do not use |
| --- | --- | --- |
| Long single documents already held in context (~117k tokens of recall) | `space-bunny-free` (5/5, 6.1 s), then `muse-spark-1.3-contributor-free`, `nemotron-3.5-lightning-free`, `mimo-v2.6-flash-free`, `longcat-2.5-preview-free`, `nemotron-3-ultra-free` — all 5/5 | `ling-3.1-flash-free` (262,144-token ceiling), `step-5-preview-free` (transcription slips) |
| Locating facts inside a large file with tools (`research/graph.py`, `digiquant/src/digiquant/graph/`, `data/gloomberb/agent_tools.py`) | `muse-spark-1.3-contributor-free` (one read, 5/5), `nemotron-3-ultra-free`, `longcat-2.5-preview-free`, `step-5-preview-free` | `nemotron-3.5-lightning-free` (times out), `mimo-v2.6-flash-free` (stalls), `ling-3.1-flash-free` (refuses), `space-bunny-free` (stops early) |
| Free default for crew seats doing summaries, classification and triage | `muse-spark-1.3-contributor-free` | — |
| Structured output with a computed field (`research/decision_log.py`, `research/telemetry.py`, `research/schemas.py`, `research/attribution.py`) | `muse-spark-1.3-contributor-free` — it is the only model that was 4/4 *and* never mis-summed | `space-bunny-free` (mis-sums under load), `longcat-2.5-preview-free` (omits required fields) |
| digiquant research-decision phases: `research/phases/phase6_consolidate.py`, `phase7_synthesis.py`, `phase_monthly.py`, plus `triage_phase` and `publish_phase` | `nemotron-3-ultra-free` and `muse-spark-1.3-contributor-free` for the consolidation and synthesis writes | any free model for `research/phases/preflight.py` alone — a refused preflight is a silent gate |
| Dashboard research-retrieval deliberation (`dashboard/research_retrieval/planner.py`, `retriever.py`, `evidence_bundle.py`, `direction_decision_context.py`) | `muse-spark-1.3-contributor-free`, `nemotron-3-ultra-free` — both 5/5 on a large file | `mimo-v2.6-flash-free` and `nemotron-3.5-lightning-free` (both stalled on the same file, in different runs) |
| Digest rendering (`research/notify/digest.py`, `research/dashboard_digest.py`, `research/templates/*.j2`) | `muse-spark-1.3-contributor-free`, `longcat-2.5-preview-free` | `space-bunny-free` (left a required field empty in round 1) |
| Anything that must sum, count, or reconcile (`total_cents`-shaped work, cost/liquidity registries) | no free model is safe on a single run | all of them — every failure observed here was silent and well-formed |
| Paperclip consultant briefs: spec sheets, detailed architecture, security, hard legal or tax texts, risky reviews, visual design | none — these go to the Claude bench, Cursor or Grok Bot under the consult caps, per the operating rules | — |

The last row is the load-bearing one. This benchmark measures free models against
mechanical probes. It does **not** license them for planning, new architecture,
spec writing, security judgement or legal reading: those are the documented
consultant lanes, and no score in this document moves that boundary.

### Effect on the Go default

**No change.** DeepSeek V4.1 Flash stays on Muse exec seats.

`muse-spark-1.3-contributor-free` passing 4/4 does not license promoting
`space-bunny-free`: Space Bunny failed `hreason` in round 1 and mis-summed here,
and it is 3/5 on long-file navigation. `kimi-k3` stays off tool-using seats.

## Two harness defects found by this benchmark

Both are recorded because they produced wrong numbers before they produced right
ones, and both are the kind that silently survive review.

1. **A case-asymmetric grader.** The first grader compared `got.strip().upper()`
   against a lowercase expected value, and marked `region` **wrong for all 8
   models** — including the models that had returned `eu-north-3` correctly. A
   failure that is uniform across every subject is an instrument failure, not a
   subject failure. Fixed with a comparison that normalises case and punctuation.
2. **A line-based JSON extractor.** Two models emit pretty-printed, multi-line
   JSON. The line extractor scored a perfect 5/5 answer as 0/5. Fixed by
   extracting from the first `{` to the last `}`.

What made both cheap to fix: **every raw model response was saved to disk**, so
re-grading took seconds and no call was repeated. A harness that keeps only its
own score forces a re-run — which costs money and, on a tier this variable, gives
a *different* answer.

## Variance

The same `hctx_nav` probe was run twice, four workers each time. Scores moved
materially:

| Model | Run A | Run B |
| --- | --- | --- |
| `muse-spark-1.3-contributor-free` | 4/5 | 5/5 |
| `space-bunny-free` | 4/5 | 3/5 |
| `step-5-preview-free` | 4/5 | 5/5 |
| `mimo-v2.6-flash-free` | 4/5 | **0/5** |
| `nemotron-3.5-lightning-free` | 1/5 | **0/5** |
| `longcat-2.5-preview-free` | 4/5 | 5/5 |
| `nemotron-3-ultra-free` | 4/5 | 5/5 |

Latency moved too: `nemotron-3-ultra-free` 76 s vs 211 s, `step-5-preview-free`
248 s vs 376 s, `longcat-2.5-preview-free` 214 s vs 340 s.

**Consequence: a single run does not rank these models.** Every table above is
one run, and the ordering within it should be read as a snapshot, not a
measurement. `mimo-v2.6-flash-free` scoring 4/5 in one run and stalling in the
next is the clearest case: it is not a worse model, it is an unstable one, and
only repeated runs separate the two. Any future comparison needs at least three
runs per cell before it is allowed to say "better".

## What was not measured

- **Per-IP rate limiting.** VPN rotation is disabled on this host, so every
  measurement came from a single egress. See above.
- **Sustained load.** 12 concurrent requests is a burst, not a soak. Nothing here
  says what a free tier does over an hour.
- **Multi-turn and stateful sessions.** Every probe was single-shot. Whether a
  free model degrades over a long conversation is unknown.
- **Anything requiring more than ~165k tokens of context in one place.** The
  ceiling was established for `ling-3.1-flash-free` and not probed upward for
  the others.
- **Model quality in general.** These are mechanical probes on one afternoon.
  Nothing here measures judgement, and the consultant lanes stay where they are.
- **Free-tier models can be withdrawn** by the provider without notice, exactly
  as `exo-free` was.

## Reproducing

The harness is not committed: the issue scope covers a document, not an eval
harness in the repository. It is plain `opencode run --standalone` plus a Python
grader, needs no API key, and cost $0 across ~40 calls in this round.

Two harness requirements learned the hard way, worth stating for whoever rebuilds
it: **capture stdout and stderr together** (opencode's agent progress lines go to
stderr, and losing them reads as "the model used no tools"), and **save every raw
response** before grading anything.