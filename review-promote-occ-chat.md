# Review — `promote/occ-chat` @ `1a2220a48`

- **Reviewer:** in-session review subagent (fresh context; did not author the commit)
- **Subject:** `1a2220a48` — "feat(occ): carve multilingual ticket search out to main"
- **Base:** `origin/main` @ `c060cd37e`
- **Worktree:** `/Users/chrisstefan/Code/digithings/.worktrees/occ-promote`
- **Diff:** 41 files, +3224 / −150
- **Verdict:** **request-changes**
- **Severity counts:** blocking **1** · major **2** · minor **4** · info **5**

## Scope of this pass

The commit carries 6 review files (`review-4945.md`, `review-4946.md`, `review-4956.md`,
`review-4962.md`, `review-4963.md`). `grep` confirms **none of them** mentions
`occ_tickets.jsonl`, `build_occ_tickets_seed`, `seed_chroma.sh`, or `start_digisearch.sh`
— i.e. the seed/ingest/deploy plumbing (priority items 1–4 below) is genuinely unreviewed
work. That is where this pass concentrates.

---

## Blocking

### B1 — `start_digisearch.sh` still waits on the **v4** marker after the seed moved to v5

- `apps/digithings-stack-cloudflare/container/seed_chroma.sh:31` — `SEED_VER="v5"` (bumped, correct)
- `apps/digithings-stack-cloudflare/container/start_digisearch.sh:23` — `SEED_VER="v4"` (**stale**)

The two scripts must agree on the marker name; they now do not. Concretely, on every
container cold boot:

1. `seed_chroma.sh` succeeds and writes `.stack_chroma_seeded_v5`, then **explicitly
   deletes** the v4 marker — `seed_chroma.sh:98-104` (`rm -f … .stack_chroma_seeded_v4`).
2. `start_digisearch.sh:34` spins on `while [ ! -f "${DATA_CHROMA}/.stack_chroma_seeded_v4" ]`.
   That file can no longer ever exist.
3. The escape hatch on seed failure also misses: `SEED_FAILED` is
   `.stack_chroma_seed_failed_v4` (`start_digisearch.sh:25`) but `seed_chroma.sh:115`
   only ever touches `…_v5`. So the `break` at `start_digisearch.sh:35-38` never fires.
4. Result: the loop always runs to `start_digisearch.sh:40` (`i > 180`) → **a flat 180 s
   (3 min) added to every boot** before digisearch binds :8002, and the only log line is
   `start_digisearch.sh:41` "WARN chroma seed v4 wait timed out (no success or failure
   marker)" — which is **false**: the seed succeeded.

Two distinct production degradations in one:

- **Latency:** 3 minutes of dead wait on every cold boot of the OCC stack.
- **Lost failure signal, exactly the class this review was asked to hunt.** The comment at
  `start_digisearch.sh:29-32` promises a loud "FAILED; digisearch will start
  unseeded/partial" warning. A *real* ingest failure now produces only the generic
  timeout warning instead, so an operator sees "timed out, no marker" when the truth is
  "seed errored". The docstring at `seed_chroma.sh:109-112` ("no SEED_MARKER is written, so
  this boot's start_digisearch.sh will not see a success marker (… logged loudly there)")
  is now untrue in both directions.

It also defeats the wait's stated purpose — holding digisearch back while CLI ingest holds
the Chroma SQLite lock (`start_digisearch.sh:2-3`) — turning a deliberate gate into an
unrelated 180 s sleep that happens to expire after seeding. Correctness of the *ordering*
is preserved by luck of timing, not by the check.

No test pins the two `SEED_VER` values together (`grep -rn "SEED_VER" tests/` → nothing),
and no prior review caught it.

**Fix:** set `start_digisearch.sh:23` to `SEED_VER="v5"`, and add a test that asserts the
`SEED_VER` literal is identical in `seed_chroma.sh` and `start_digisearch.sh` so the next
bump cannot half-land again.

---

## Major

### M1 — Profile A flips to the `occ_help,occ_tickets` fan-out but never sets the provider: write and read paths disagree on the vector space

- `infra/digichat-release/compose.profile-a-bundle.override.yml:6` — `DIGI_TENANT_CORPUS_MAP` → `"occ_help,occ_tickets"`
- `infra/digichat-release/.env.profile-a-bundle.example:52` — same flip
- `infra/digichat-release/compose.profile-a-bundle.yml`, `compose.profile-a.yml`, `.env.profile-a-bundle.example` — **no `DIGISEARCH_EMBEDDING_PROVIDER` anywhere** (`grep -rn "DIGISEARCH" infra/digichat-release/compose.profile-a*.yml` returns only `DIGISEARCH_URL`)

The Cloudflare path is fine: `wrangler.toml:283` and `src/index.ts:130` both set the
model id, and supervisord passes that env to both the seed and the server. **Profile A
does not**, and in that profile the two paths resolve *different* models:

| Path | Resolution | Result |
|---|---|---|
| Write (`seed_chroma.sh:79-80` → `ingest_snapshot` → `multilingual_index`) | env unset → pinned to `MULTILINGUAL_MODEL_ID` at `scripts/index_occ_tickets.py:235-236` | `occ_tickets` stamped **multilingual** |
| Read (`digisearch` server → `_stub.py:146-148` → `resolve_backend_embedding_provider`) | env unset → `factory.py:203-204` `if name is None: name = "minilm"` | queries embed as **minilm** |

`occ_tickets` is then stamped with a model id the query path does not use, and
`ChromaBackend` asserts on it at construction — `chroma.py:139` raises
`EmbeddingModelMismatchError`. That type is deliberately **not** a `ValueError`/
`RuntimeError` (`chroma_errors.py` docstring; `backend_errors.py` same for
`SearchBackendError`), so it is not in `_BACKEND_ERRORS` (`_stub.py:35`); `_stub.py:175`
re-wraps it as `SearchBackendError`, which also escapes `_BACKEND_ERRORS`. It therefore
propagates out of the fan-out comprehension at `_stub.py:346`.

**Blast radius is larger than "ticket search breaks":** because the fan-out is a bare list
comprehension with no per-index isolation, a failure on `occ_tickets` takes **`occ_help`
down with it** — the entire OCC corpus retrieval 500s, not just the new half. That is the
opposite of the degradation the code intends (`seed_chroma.sh:69-71`: "OCC then answers
from occ_help alone").

Fix: add `DIGISEARCH_EMBEDDING_PROVIDER: "Xenova/paraphrase-multilingual-MiniLM-L12-v2"`
to the `digithings-stack` service in `compose.profile-a-bundle.yml` (and document it in
`.env.profile-a-bundle.example`), so Profile A matches the Cloudflare deployment.

### M2 — 1.5 MB of unmasked third-party PII + 372 internal notes committed to the public mirror and baked into a public image

- `apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl` — new, 919 rows, 1 518 223 bytes

Verified contents (aggregate only, no PII reproduced here):

- 86 distinct named customer contacts (`customer_name` populated on all 919 rows)
- 47 distinct named organizations; 8+ distinct real corporate customer email domains
  (German Mittelstand businesses), leading counts 88 / 57 / 32 / 30
- **372 rows with `internal: true`** — internal support notes, all 372 correctly tagged
  `[internal]` in `content`, spread over 158 tickets that mix internal and public articles
- Chat surface is ungated: `compose.profile-a-bundle.override.yml` /
  `.env.profile-a-bundle.example` set `occ.digithings.ai` `gateMode: ungated`, and the
  shipped system prompt now **promises** disclosure —
  `src/index.ts:130` / `wrangler.toml:293`: "customer names and emails are shown in full
  (demo mode); internal ticket notes are included and tagged [internal]".

The demo-mode decision itself was reviewed for the MCP tools (#4944/#4945, per the
in-repo `review-4945.md`). What is **new in this commit** is the transport: the same PII
now lives in git on the public GitHub mirror (AGENTS.md: "GitHub stays the public face")
and inside the container image at `/seed/occ_tickets.jsonl` (`Dockerfile:177` copies the
whole `container/seed` tree), served to anonymous internet users.

The only automated gate does not catch it — verified:

```
$ gitleaks detect --config .gitleaks.toml --source . --log-opts="origin/main..HEAD" --redact
1 commits scanned … no leaks found
```

`.gitleaks.toml` has no allowlist or rule for this path, and no test asserts the payload
is synthetic. This needs an explicit human decision on the record before promotion to
`main`: either the data is confirmed non-sensitive demo/fixture data (in which case a
`README`/generator note saying so would prevent the next reader from re-litigating it), or
the payload should be scrubbed/synthesized before it rides the public mirror. Per
AGENTS.md this is exactly the kind of thing that should not merge on CI-green alone.

---

## Minor

### m1 — `query_index` docstring overstates per-index error isolation

`digisearch/src/digisearch/search/_stub.py:341-347`. "Backend errors still propagate per
index (fail-closed, never answered from a different corpus)" — the fail-closed half is
correct and verified (`SearchBackendError` escapes `_BACKEND_ERRORS`), but "per index"
reads as isolation, and it is not: `_stub.py:346` is a bare comprehension, so the first
failing index aborts the merged query for all of them. This is the mechanism behind M1.
Wording should say so explicitly.

### m2 — snapshot-integrity test would not catch a line-boundary truncation

`tests/scripts/test_build_occ_tickets_seed.py:152-167`. `json.loads` per line does catch
mid-line corruption (a truncated final line raises). But the only volume guard is
`assert len(rows) > 100` (`:163`) — a payload truncated at a line boundary down to 200 of
919 rows still passes, silently losing ~78 % of the corpus. Pin the expected row count
(919) or a checksum against `.seed_build_id`.

### m3 — the same test never asserts the metadata fields the chat surface depends on

`tests/scripts/test_build_occ_tickets_seed.py:164-167` checks top-level keys and id
uniqueness, then only `any(...)` for `internal` and `customer` — existence somewhere, not
coverage. Nothing pins `number`, `customer_name`, `group`, `organization`, `owner`,
`priority`, `article_index`, `article_type`, nor that `metadata` is a dict. I verified all
919 rows carry all ten fields today (`:1` — they do), so this is a regression-guard gap,
not a live defect.

### m4 — model-stamp verification is silently skipped when no Chroma location is configured

`scripts/index_occ_tickets.py:283-286`: with neither `CHROMA_PATH` nor `CHROMA_HOST`, the
function `return`s with **no log line at all**, so "verification ran" is
indistinguishable from "verification was skipped". The Vectorize leg above it does log
(`:281`). A one-line `print` on the skip branch would make the check honest. (In the
container this is not hit: `seed_chroma.sh:79` exports `CHROMA_PATH`.)

---

## Info

### i1 — Model weights are not baked; every cold boot pulls ~120 MB from HF Hub

`Dockerfile:84-89` comments that the weights *can* be baked with
`scripts/download_multilingual_model.py` + `DIGISEARCH_MULTILINGUAL_MODEL_DIR`, but no
such `RUN` step exists and no `DIGISEARCH_MULTILINGUAL_MODEL_DIR` is set in the image, so
`multilingual.py:98-119` hits `snapshot_download` on first embed — i.e. on the seed
critical path, before digisearch starts. Failure is **loud**, not silent
(`RuntimeError` → `WARN … seed failed` → `ERROR … incomplete` → `exit 1`), which is what
matters most here, but it is a new runtime egress dependency on every boot with no bake
step. Consider a `RUN` pre-warm + `HF_HUB_OFFLINE=1`.

### i2 — Missing payload fails open, and the fan-out then loses ticket search with only a boot-time WARN

`seed_chroma.sh:74-77` returns 0 when `/seed/occ_tickets.jsonl` is absent, so `ok` stays 1
and `SEED_MARKER` is written — the index is never written *and* never retried. This matches
`seed_index`'s tolerance (`seed_chroma.sh:59-62`) and is a defensible choice; the query
side degrades benignly (a query on an absent collection does `get_or_create_collection`
→ 0 hits, no error, so OCC still answers from `occ_help`). Verified `/seed/occ_tickets.jsonl`
*is* in the image today (`Dockerfile:177` copies the whole `container/seed` dir; no
`.dockerignore` rule excludes `*.jsonl`), so this only bites a rebuild without the payload.

### i3 — `seed_tickets` env wiring is correct

`seed_chroma.sh:79-80` passes `CHROMA_PATH="$DATA_CHROMA"` and `DIGISEARCH_ALLOW_STUB=0`;
the provider comes from the container env set at `wrangler.toml:283` / `index.ts:130` and
inherited through supervisord — i.e. the **same** value the query path uses. The
provider-agreement guard is real, not incidental: `multilingual_index`
(`scripts/index_occ_tickets.py:238-247`) resolves the backend provider and refuses loud
(`SystemExit`) on anything that is not a `MultilingualEmbedder` rather than stamping a
wrong model id over same-dim vectors. `sh -n` clean on both shell scripts. Under
`set -eu`, the `if ! seed_tickets …` guard correctly prevents `-e` from aborting on the
non-zero return.

### i4 — Dockerfile COPY paths resolve

`Dockerfile:110-111` copies the two modules to `/app/scripts/`; `WORKDIR /app` +
`python3 -m scripts.build_occ_tickets_seed` makes `scripts` an implicit namespace package
(no `__init__.py` needed), and the function-level
`from scripts.index_occ_tickets import multilingual_index`
(`build_occ_tickets_seed.py:103`) resolves on the same `sys.path`. The ingest path never
imports `scripts.zammad_mcp` (only `build_snapshot` does), so the container does not need
it on that path. `sh -n` + import graph consistent.

### i5 — `download_multilingual_model.py` env-var shadowing

`scripts/download_multilingual_model.py:33` reads `os.environ["MULTILINGUAL_MODEL_ID"]` —
the same name as the module constant it defaults to. `--model-id` also overrides the repo
while `allow_patterns` (`:48`) still assumes the Xenova file layout, so a different
`--model-id` fails later at the "download incomplete" check rather than up front. Cosmetic.

---

## Verified clean (no finding)

**`occ_tickets.jsonl` integrity — all checks pass.** Parsed all 919 lines: 919/919 valid
JSON objects, 0 blank lines, no CR, trailing newline present, no extra top-level keys
(exactly `{id, doc_id, content, metadata}`), all 919 ids unique and matching
`zammad-<ticket>-<n>`, all 919 `doc_id` values equal `zammad-ticket-<ticket_id>`, 185
distinct tickets (max 22 articles/ticket), `article_index` 1-based and contiguous per
ticket, 0 empty `content` rows, content length 75–20 164 chars. All ten chat-relevant
metadata fields present on all 919 rows (`number`, `customer`, `customer_name`,
`internal`, `group`, `organization`, `owner`, `priority`, `article_index`,
`article_type`). `internal` is a real bool on all 919 (372 `true` / 547 `false`, none
non-bool) and all 372 `true` rows carry the `[internal]` tag in `content`, consistent with
`build_ticket_chunks` (`index_occ_tickets.py:88-91`).

**`multilingual_index` pin/restore semantics are correct on every exit path.**
`scripts/index_occ_tickets.py:248-255` uses `try/finally`, so the env is restored on the
normal path, on an exception from `index_chunks`, and on an exception raised by the
caller's `with` body. The restore distinguishes `None` (pop) from a preset (re-assign), so
a caller's pre-set value is preserved exactly. Verification runs **after** the write and
**after** restoration (`:257`), and — importantly — it is *not* reached when the body
raises, which is the correct ordering (it does not verify a collection whose write
aborted). It constructs `ChromaBackend` with the multilingual embedder explicitly
(`:294-300`), so it does not depend on the already-restored env var. No path writes an
empty collection: `ingest_snapshot` refuses an empty payload
(`build_occ_tickets_seed.py:108-109`), `index_chunks` → `route_add_chunks` uses
`get_or_create_collection` and never deletes, and `build_snapshot` refuses to write a
0-article payload (`build_occ_tickets_seed.py:161-162`).

**JSONL reader rejects malformed input with actionable errors.**
`build_occ_tickets_seed.py:83-89` raises `SystemExit` naming the file, the 1-based line
number, and either the JSON decode error or the sorted list of missing keys. Covered by
`test_read_snapshot_rejects_malformed_rows_with_line_numbers`.

**The three tenant-map copies are byte-consistent after decoding.** Parsed each with its
own real parser (TS single-quote unescape, `tomllib`, `yaml.safe_load`) and compared
canonicalised JSON: `src/index.ts` ≡ `wrangler.toml` ≡
`compose.profile-a-bundle.override.yml`, all resolving to
`occ.digisearchIndex: "occ_help,occ_tickets"` and an identical 46-newline
`researchSystemPrompt`. `.env.profile-a-bundle.example:52` differs only in that it carries
no `researchSystemPrompt` — pre-existing, not introduced here.
`DIGICHAT_EMBED_TENANTS` is consistent between the compose override and the `.env`
example, with `occ.digithings.ai.backend.digisearchIndex = "occ_help,occ_tickets"` in
both. `tests/dg/test_tenant_corpus_parity.py` pins the reduced map.

**The multilingual model id string is identical at every occurrence**
(checked repo-wide, excluding `.venv`/`node_modules`): the canonical definition
`digisearch/src/digisearch/embedding/providers/multilingual.py:22`, the factory's
lowercased dispatch key `factory.py:129`, the container defaults
`src/index.ts:130` and `wrangler.toml:283`, and the doc/error-string mentions in
`index_occ_tickets.py`, `scripts/zammad_mcp/README.md`, `digisearch/ARCHITECTURE.md`,
`factory.py:152`. No typos, no near-duplicates. `tests/ds/test_multilingual_embedder.py:76`
pins the literal against `MULTILINGUAL_MODEL_ID`.

**Tests pass and do cover the safety properties, not just happy paths.**
`pytest tests/scripts/test_build_occ_tickets_seed.py tests/ds/test_multi_index_query.py
tests/ds/test_multilingual_embedder.py` → **29 passed**;
`tests/dg/test_corpus_routing.py tests/dg/test_tenant_corpus_parity.py
tests/scripts/test_vectorize_sync.py` → **60 passed**. The provider pin/restore is
asserted at `tests/ds/test_multilingual_embedder.py:318` (model id seen by the backend
during indexing) and `:320` (env absent afterwards); the conflicting-preset refusal is
asserted at `:354-357` (`SystemExit` **and** the preset left exactly as found).
`test_corpus_routing.py` proves the new `_INDEX` regex accepts `occ_help,occ_tickets` and
rejects `occ_help,`, `,occ_help`, `occ_help,,occ_tickets`, `occ help,occ_tickets`.
Gap noted for completeness: there is no test for the `finally` restore when
`index_chunks` **raises** — the code is correct by construction, so this is a coverage
note, not a defect.

**`corpus_routing.py` regex is tight.** `_INDEX`
(`digigraph/src/digigraph/corpus_routing.py:36`) anchors both ends, requires each element
to match the original single-index shape, and rejects empty elements — so the fan-out
cannot smuggle a path separator, whitespace, or a leading/trailing comma past validation.

**Unrelated worktree note (not part of the commit).** `tests/scripts/test_build_occ_tickets_seed.py`
has an uncommitted `ruff format`-only diff in this worktree (line wrapping at `:37-40`,
`:53-55`, `:158-162`, and a dropped `# noqa: ANN001, ANN202` at `:112`). It is
cosmetic and not in `1a2220a48`, but it will show up as a dirty file on any re-push.

---

## Summary for the merge decision

`request-changes`. Two of the three substantive findings are in the deploy plumbing that
no earlier review touched, and both are the exact failure mode this pass was asked to
hunt — a write/read disagreement on the embedding model (M1) and a seed step whose
completion signal the runtime no longer looks for (B1). B1 is a one-line fix plus a test
that pins the two `SEED_VER`s together; M1 is one env var in the Profile A compose.
M2 needs a human decision on the record rather than a code change.

---

## Responses (author, 2026-10-02)

| ID | Severity | Disposition | Resolution |
|----|----------|-------------|------------|
| B1 | blocking | **fixed** | `container/start_digisearch.sh:23` → `SEED_VER="v5"`, with a comment naming the marker-delete coupling, the 180 s timeout cost of drift, and the new test that pins it. |
| M1 | major | **fixed** | `DIGISEARCH_EMBEDDING_PROVIDER` added to the compose override's `digithings-stack.environment` and to `.env.profile-a-bundle.example`, both set to the multilingual model id and both commented to stay in sync with `wrangler.toml [vars]`. Also documents that the provider is global, not per-index, and that `EmbeddingModelMismatchError` escapes `_BACKEND_ERRORS` so it aborts the whole fan-out leg list. |
| M2 | major | **accepted** | Real, deliberate, and the owner's explicit choice: the snapshot approach was selected over a boot-time backfill after being told the snapshot publishes 86 named contacts, 47 organizations, and 372 internal notes to the public mirror and image. gitleaks does not catch plain emails, so CI will not flag it — the risk is documented in the commit body instead. Reversing it means moving to the boot-time backfill and deleting the payload. |
| a | minor | **fixed** | `digisearch/src/digisearch/search/_stub.py` `query_index()` docstring now states fan-out is *not* per-index fault isolation: `_BACKEND_ERRORS` degrade one leg to empty, anything outside it aborts the comprehension. |
| b | minor | **fixed** | `test_committed_snapshot_parses_and_covers_tickets` raised to `len(rows) > 500` and `> 500_000` raw bytes with a no-trailing-blank-line assertion, so line-boundary truncation cannot pass. |
| c | minor | **fixed** | Same test now asserts a `required_metadata` set (number, customer, customer_name, internal, group, organization, owner, priority, article_index, article_type) on **every** row. |
| d | minor | **fixed** | `_verify_collection_model` logs a note when no Chroma location is configured instead of returning silently. |
| — | new | **added** | `tests/scripts/test_stack_seed_config_parity.py` pins both drift classes: `SEED_VER` agreement between seeder and waiter, cleanup of every prior marker, the provider pinned on both runtime layers, and the env example documenting the same id. |

### Re-verification after the fixes
- `pytest tests/scripts/test_stack_seed_config_parity.py tests/scripts/test_build_occ_tickets_seed.py tests/scripts/test_check_tenant_corpus_map.py -q` → 29 passed.
- `pytest tests/scripts/ tests/ds/ tests/dg/ -q` → 3709 passed, 1 failed, 78 skipped. The single failure is `tests/ds/test_chonkie_chunking.py::test_get_chunker_backend_semantic_and_token`, **pre-existing on `origin/main`** (verified in a throwaway worktree at `c060cd37e`: same `ImportError: model2vec is not available`), caused by a missing optional dependency in the local venv, not by this branch.
- `ruff check scripts/ tests/scripts/test_build_occ_tickets_seed.py tests/scripts/test_stack_seed_config_parity.py digisearch/src/digisearch/search/_stub.py` → All checks passed; `ruff format` → 4 files unchanged.
- `make doc-check` → OK (439 markdown files).
- `gitleaks detect --no-git --source . --config .gitleaks.toml` → no leaks found (32.48 MB scanned).
