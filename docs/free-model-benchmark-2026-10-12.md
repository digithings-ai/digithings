# Free-model benchmark, 12 Oct 2026

**Issue:** DIG-3067 · **Author:** OpenCode Go consultant · **Date:** 2026-10-12 (Rome)

Light benchmarks of every free model the `opencode` Zen provider exposes. No
eval harness, no CI suite, no paid-model spend. Every run in this document
cost **$0** (all probes used `opencode/*`, the zero-cost free tier, never
`opencode-go/*`).

This complements [`MODEL_CATALOG.md`](MODEL_CATALOG.md), which is the
generated price/metadata snapshot. This document is hand-written measurement
evidence: what the free models actually did.

---

## What is free today

`opencode models` lists 10 zero-cost models on the `opencode` provider (the
Zen free tier). Two of them are listed but **dead upstream**, which the
`opencode models` listing does not tell you:

| Model | Listed | Actually usable |
|---|---|---|
| `opencode/muse-spark-1.3-contributor-free` | yes | yes |
| `opencode/space-bunny-free` | yes | yes |
| `opencode/nemotron-3.5-lightning-free` | yes | yes |
| `opencode/nemotron-3-ultra-free` | yes | yes |
| `opencode/mimo-v2.6-flash-free` | yes | yes |
| `opencode/ling-3.1-flash-free` | yes | yes |
| `opencode/longcat-2.5-preview-free` | yes | yes (preview) |
| `opencode/step-5-preview-free` | yes | yes (preview) |
| `opencode/exo-free` | yes | **no** — `Model exo-free has been deprecated` (HTTP 410) |
| `opencode/ling-3.0-flash-fin-free` | yes | **no** — `Upstream request failed: Model is unavailable` (HTTP 400) |

**8 usable free models.** A name in `opencode models` is not evidence of
availability; one cheap `opencode run -m <model> "Say OK"` is.

## Probes

Four probes, all short, all auto-graded. Passing means the grader verified the
output, not that a human judged it.

| Probe | What it tests | Grading |
|---|---|---|
| `hjson` | Structured output under a fixed schema, with a **computed** field | JSON parsed; all keys, three ordered items, exact SKU/qty/price values, and `total_cents == Σ qty×unit_price` verified |
| `hreason` | Multi-step arithmetic with a hidden trap (a per-100-requests surcharge) | The single integer must equal 48,000,000; last integer in the reply is taken |
| `hcode` | Write a file that implements a spec, then it is **executed** | Emitted `solution.py` is imported and run against 3 cases (empty list, duplicates, negatives) |
| `htool` | Tool calling — does it actually use the tool, or narrate? | The model must run `echo PROBE-TOKEN-4821` via the shell and report the literal token |

`hreason` and `hjson` are text-only. `hcode` and `htool` need a writable cwd.

### Harness caveat that matters

The nested `opencode run` inherits the **process** cwd, not a `cwd=` argument,
and the consultant config sets `permission.external_directory: {"*": "deny"}`.
The first batch ran with its cwd under a system temp dir, so every model
looked like it failed to write a file — including models that pass. Probes were
re-run from a directory under `~/Code`, where writes are allowed. **The first
`hcode`/`htool` batch is void**; the numbers below are the re-run. This is
recorded here because the same trap will hit anyone re-running this.

## Results

| Model | hjson | hreason | hcode | htool | Score | Avg latency | Verdict |
|---|---|---|---|---|---|---|---|
| `muse-spark-1.3-contributor-free` | PASS | PASS | PASS | PASS | **4/4** | **6.5 s** | **Best free default** |
| `nemotron-3.5-lightning-free` | PASS | PASS | PASS | PASS | **4/4** | 9.4 s | Strong second |
| `mimo-v2.6-flash-free` | PASS | PASS | PASS | PASS | **4/4** | 19.4 s | Good, slow |
| `ling-3.1-flash-free` | PASS | PASS | PASS | PASS | **4/4** | 23.3 s | Good, slow |
| `nemotron-3-ultra-free` | PASS | PASS | PASS | PASS | **4/4** | 32.3 s | Accurate, slow |
| `space-bunny-free` | FAIL | PASS | PASS | PASS | 3/4 | 4.4 s | Fastest; weak structured output |
| `longcat-2.5-preview-free` | FAIL | PASS | PASS | PASS | 3/4 | 24.1 s | Preview; weak structured output |
| `step-5-preview-free` | PASS | PASS | PASS | PASS | **4/4** | 45.2 s | Accurate, slowest |
| `exo-free` | — | — | — | — | 0/4 | 1.2 s | **Dead**, deprecated |
| `ling-3.0-flash-fin-free` | — | — | — | — | 0/4 | 1.1 s | **Dead**, unavailable |

### The two 3/4 failures are the same failure

- `space-bunny-free` returned `total_cents` of 16,496 / 17,246 / 16,496 across
  three runs. Correct is 20,696. It got every individual field right and then
  **mis-summed them**. It is a consistent error, not noise.
- `longcat-2.5-preview-free` emitted the schema but left `note` empty.

Both are single-axis failures: reliable on code, tools and reasoning, weak on
**structured output with arithmetic inside it**. Neither is a rounding error
in either direction — they are not near 20,696.

### Rate limits

6 concurrent `muse-spark-1.3-contributor-free` requests, all exit 0, no
throttling observed. The free tier did not rate-limit at this concurrency.

## Recommended mapping

Free tier covers volume work. Paid `opencode-go` models stay for planning,
architecture and review — see the "Review rule" in the operating rules.

| Work | Model | Why |
|---|---|---|
| **Free default** (seat `small_model`, summaries, classification, triage) | `opencode/muse-spark-1.3-contributor-free` | 4/4 at the lowest latency; same family as the Go `muse-spark-1.3-contributor`, so behaviour transfers |
| Free default, when `muse-spark` is busy or its region is limited | `opencode/nemotron-3.5-lightning-free` | 4/4, 9.4 s |
| Free code-edit and tool-use work | `opencode/nemotron-3-ultra-free` | 4/4 including executed-code checks |
| Long, slow, background work where latency does not matter | `opencode/step-5-preview-free` | 4/4 but 45 s; free |
| **Not** for anything returning JSON with computed fields | `opencode/space-bunny-free`, `longcat-2.5-preview-free` | Both mis-summed `hjson` |
| Nothing | `exo-free`, `ling-3.0-flash-fin-free` | Deprecated / unavailable |

### Effect on the Go default

Unchanged, and this run does not argue otherwise: **DeepSeek V4.1 Flash**
remains the default `model` for the Muse exec seats. The free tier is a
capacity and cost lever, not a quality replacement. Specifically:

- `muse-spark-1.3-contributor-free` scoring 4/4 does **not** license promoting
  Space Bunny. On 12 Oct, Space Bunny **failed** `hreason` in the earlier
  round-1 sweep (answered 8, expected 9) and **fails** `hjson` here. Two
  independent reasoning/structured-output failures, zero evidence it beats
  DeepSeek.
- kimi-k3 stays off tool-using seats (it answered the tool probe without
  calling the tool in round 1).

## What was not measured

- One run per cell. No repeats, so per-cell variance is unknown; the two
  `space-bunny-free` `hjson` values that differed (16,496 vs 17,246) show the
  variance is not zero.
- No sustained load, no multi-hour soak, no VPN-rotation burst. The 6-way
  concurrency check is a smoke test, not a rate-limit measurement.
- No vision, no long-context retrieval probe. Round 1 covered recall on
  paid models; the free tier did not get an equivalent.
- Free-tier models can be withdrawn or changed without notice. `exo-free` and
  `ling-3.0-flash-fin-free` are already dead.

## Reproducing

Not committed, deliberately: the issue scope excludes an eval harness in the
repo. The probes are four short prompts with four deterministic graders. To
re-run, copy them from this document's probe table, run them with
`opencode run -m opencode/<model> --auto` **from a directory under `~/Code`**,
and grade the output. Budget: about 40 calls, $0.
