# 0025. Multilingual embedding migration for occ_help, via blue/green cutover

## Status

Proposed -- 2026-08-17

## Context

`occ_help` is a bilingual EN/DE compliance help-center corpus retrieved
through digisearch's Chroma backend (seeded by
`frontend/digithings-stack-cloudflare/container/seed_chroma.sh`). digisearch
ships a working `EmbeddingProvider` abstraction --
`digisearch/src/digisearch/embedding/base.py` defines the interface,
`embedding/providers/minilm.py` and `embedding/providers/openai.py`
implement it -- but it is never wired into the Chroma path.

`digisearch/src/digisearch/indexes/backends/chroma.py` accepts an
`embedding_provider` constructor argument (line 35) and stores it (line 43,
`self.embedding_provider = embedding_provider`), but neither `add()` (56-97)
nor `query()` (99-171) ever reads that attribute or calls `.embed()` on it.
All three `ChromaBackend(...)` construction sites in
`digisearch/src/digisearch/search/_stub.py` (lines 129, 267, 284) pass no
`embedding_provider` at all. With nothing supplying vectors, Chroma falls
back to its own bundled default: the ONNX `all-MiniLM-L6-v2` model, 384-dim,
English-only. Every document and every query in `occ_help` is silently
embedded by that model today, regardless of language. This is a
representation problem -- German text is poorly placed in the vector space
relative to English queries, and vice versa -- not a retrieval-algorithm
problem, so query-side fixes (translation, reranking) cannot fully repair
it.

Two additional silent-failure bugs were found during this investigation,
independent of the wiring gap, and they shape the fix below:

1. **The discard bug.** `chroma.py` lines 62-64:
   ```
   embeddings = [c.embedding for c in chunks if c.embedding is not None]
   if len(embeddings) != len(chunks):
       embeddings = None
   ```
   If even one chunk in a batch lacks a precomputed embedding, `add()`
   discards every embedding for the *whole* batch and falls through to
   Chroma's English-only default -- no error, no log. At matching dimension
   (e.g. a same-384-dim swap), this produces silently mixed
   English-only/multilingual vectors in one collection with no signal that
   anything went wrong. This is the dominant corruption pathway for any
   embedder migration attempted through the current code path, and it is
   the reason Decision below deliberately avoids a same-dimension embedder:
   a dimension *change* makes Chroma's own collection dimension lock reject
   a mismatched vector outright, converting this into a loud crash instead
   of a silent corruption.

2. **The stale-serving bug.** `seed_chroma.sh` writes a versioned success
   marker only on full success (`SEED_MARKER`, lines 25-26,
   `.stack_chroma_seeded_${SEED_VER}` with `SEED_VER="v4"`); on failure it
   writes a *different* marker, `SEED_FAILED` (line 30), and exits 1 without
   touching `SEED_MARKER` (lines 81-88). `start_digisearch.sh` waits for
   `SEED_MARKER`, but on seeing `SEED_FAILED` it only logs
   `WARN chroma seed v4 FAILED; digisearch will start unseeded/partial`
   (line 31) and `break`s out of the wait loop; the same file execs
   `uvicorn` unconditionally afterward regardless of which marker (if any)
   is present. A re-ingest that fails partway through -- for instance on a
   dimension mismatch during a migration -- leaves the container looking
   healthy (`/healthz` is unaffected) while serving the old, unmigrated
   collection, with the only evidence a WARN line in container logs nobody
   is tailing. This is the worst class of migration failure: confidently
   wrong, indistinguishable from success at the health-check level.

**Why hybrid fusion + reranking (candidate D) was rejected.** Four
independent judge lenses (retrieval quality, cost/ops, migration risk,
compliance/content-fidelity) each scored five candidate fixes -- (A) wire
`OpenAIEmbedder`, (B) swap in a self-hosted multilingual embedder, (C)
LLM query-translation via the existing LiteLLM integration with the
embedder untouched, (D) BM25+vector hybrid fusion plus a multilingual
reranker, (E) various staged combinations. All four judges independently
ranked D at or near last. There is no keyword/BM25 leg wired into
production today -- both Chroma and the Vectorize path are ANN-only -- so
D's "hybrid fusion" premise has only one leg to fuse against regardless of
spend. German noun-compounding (e.g. a single compound noun standing in for
an English multi-word phrase) defeats literal keyword matching outright,
independent of that gap. And a reranker can only reorder candidates already
retrieved; it cannot repair recall lost because the embedder never
represented a document well enough for it to surface in the initial
top-k. Reranking is real work, but it is not load-bearing for the defect
described above -- see Decision, Phase 4.

**Why an embedder swap is load-bearing.** All four judges converged that
some form of (B) -- swapping in a genuinely multilingual embedder -- is the
fix that actually addresses the representation problem. Candidate C
(query-translation only) fixes at most one of the four query-language /
doc-language quadrants, since a German query against English docs and an
English query against German docs need translation in opposite directions,
and a same-language query against same-language docs needs none. Candidate
C also inserts a hallucination-capable model into the semantic path of a
compliance corpus: a mistranslated defined term or modal verb (e.g. "shall"
vs. "may") can retrieve authentic, verbatim documents that answer a subtly
different regulatory question than the one asked, with nothing in the
retrieved text itself to flag the mismatch to a reader. Candidate A (wire
`OpenAIEmbedder`) fixes the wiring gap but not the language gap --
`text-embedding-3-small` is multilingual-capable but was not the model any
judge picked as primary (see disagreement 2 below), and routing a
compliance corpus through a paid third-party API is an owner/legal
decision under this project's self-hostable-and-free-by-default target
market principle, not an engineering default -- doubly so because
`occ_help` has no data-residency control once routed through a US API.

**Three disagreements, resolved by a final synthesis pass:**

1. **Embedding dimension.** The cost/ops lens preferred staying at 384-dim
   (e.g. `e5-small`) to reuse the existing collection/index name and avoid a
   re-provisioning step. The quality and compliance lenses preferred
   768/1024-dim multilingual models. Resolved against 384: the claimed
   savings are illusory once `scripts/vectorize_sync.py`'s
   `assert_index_model()` (lines 255-292) is accounted for -- it already
   refuses to upsert into an index whose stored `embedding_model` metadata
   doesn't match, so a same-dimension swap gets no free ride there either.
   More importantly, staying at 384-dim keeps the discard bug's silent
   dual-model-mixing failure mode live; changing dimension makes Chroma's
   own dimension lock reject a botched migration loudly instead. That
   fail-loud property is treated as a deliberate safety benefit of changing
   dimension, not merely a cost tradeoff to be minimized.
2. **Embedding model.** Resolved on `Alibaba-NLP/gte-multilingual-base`
   (768-dim, Apache-2.0, ~305M params): no `query:`/`passage:` prefix
   requirement (unlike the e5 family, where omitting the prefix silently
   degrades results with no error), 8192-token context, Matryoshka
   truncation available as a memory escape valve if 768-dim proves too
   costly in practice, and ONNX-inferable so it does not pull in a `torch`
   runtime dependency. This is a compromise between `bge-m3` (the quality
   lens's pick, but with a heavier runtime footprint and dense+sparse
   output the current architecture cannot use) and `e5-base`/`e5-small`
   (the cost/footprint lens's pick, but carrying the prefix-omission
   footgun). `multilingual-e5-base` is kept as the named empirical
   challenger in the Phase 0 eval, not dismissed by fiat. `bge-m3` is kept
   as a documented future upgrade path specifically for its sparse/lexical
   output, which becomes useful only once a keyword/BM25 leg exists in
   production -- it does not today.
3. **Ship LLM query-translation (candidate C) as an interim fix before the
   embedder swap lands?** Resolved against shipping it by default. The
   Phase 1 wiring fix (below) de-risks the embedder swap more directly and
   more cheaply than standing up a translation leg would, and translation
   carries the compliance risk described above. It survives only as an
   optional, additive union/RRF leg alongside the untranslated query --
   never a substitution for it -- surfaced in the citation trail, gated
   behind a flag with its own removal ticket, and only worth adding if
   pilot coverage is needed before Phase 3 ships.

The self-hostable-and-free-by-default target market principle (HuggingFace
models preferred over paid APIs, per this project's target-market notes)
applies throughout: any paid embedding or reranking API (OpenAI, Cohere) is
an owner+legal decision here, not an engineering default, because
`occ_help` is a client-pilot compliance corpus with no data-residency
control if routed through a US third-party API.

digisearch's own `ARCHITECTURE.md` (lines 1077-1088, "Schema versioning for
evidence metadata") already names this exact gap -- no mechanism exists to
detect an embedding-model mismatch between the configured spec and what an
index actually holds, and recommends storing `embedding_model_id`,
`embedding_dimensions`, and `embedding_version` in collection metadata plus
a `digisearch index reembed` CLI command. This ADR adopts that
recommendation as part of Phase 1/2 rather than inventing a separate
scheme.

## Decision

Execute the migration in five phases. Only Phase 3 requires a deploy
window; Phases 0-2 and 4 ship independently and are trivially revertible
(revert the commit; nothing external changes).

**Phase 0 -- gold eval set (effort: small, ~1-2 days).**
Build a small bilingual EN/DE gold query/relevant-document set against
`occ_help` before touching any code. This is what actually decides the
`gte-multilingual-base` vs. `multilingual-e5-base` question raised in
disagreement 2 -- empirically, not by this ADR's say-so. No production
code changes.

**Phase 1 -- behavior-preserving wiring fix + fail-loud fix + collection
metadata (effort: small, ~1 PR).**
- Wire `self.embedding_provider` into `chroma.py`'s `add()` and `query()`
  so a supplied provider's `.embed()` is actually called. This alone
  changes nothing in production yet, because no call site passes a
  provider -- it makes the abstraction load-bearing without moving the
  default.
- Fix the discard bug (lines 62-64): a partially-embedded batch should
  raise or log an error, never silently fall through to Chroma's default
  embedder. Partial-embedding batches should not be treated as "no
  embeddings supplied."
- Add `embedding_model_id`, `embedding_dimensions`, and
  `embedding_version` to Chroma collection metadata at creation time, per
  `ARCHITECTURE.md`'s existing (f) recommendation (lines 1077-1088), so
  Phase 3's cutover has something authoritative to check against instead
  of inferring model identity from vector dimension alone.
- This phase is a pure prerequisite; it does not change what model
  `occ_help` is served by.

**Phase 2 -- new multilingual `EmbeddingProvider` + ONNX spike (effort:
medium, ~1 PR + a timeboxed spike).**
- Add a new provider under `digisearch/src/digisearch/embedding/providers/`
  implementing `gte-multilingual-base` via ONNX Runtime, alongside the
  existing `minilm.py` and `openai.py` providers -- same interface
  (`embed()`, `dimensions`), defined in `embedding/base.py`.
  `multilingual-e5-base` is implemented as the challenger in the same
  spike for the Phase 0 eval, not shipped as a second production option.
- Add a new `embedding-multilingual` extra to
  `digisearch/pyproject.toml`'s `[project.optional-dependencies]`
  (alongside the existing `chroma`, `embedding`, `azure`, etc. table,
  lines 27-58) carrying the ONNX runtime dependency. No existing extra is
  touched; `embedding` (line 43, currently `openai>=1.0` only) is left as
  is.
- The ONNX spike is timeboxed. There is no repo precedent for packaging
  and running an ONNX multilingual embedding model in this codebase today
  (the only ONNX use is Chroma's own bundled default). If ONNX inference
  proves impractical (packaging size, inference latency, or missing
  operator support), fall back down the ladder: `gte-multilingual-base`
  via `torch` -> `multilingual-e5-base` (smaller, better `torch`/ONNX
  tooling precedent) -> `e5-small` multilingual variant as a last resort,
  in that order, each requiring the fallback to be named explicitly before
  substituting it, not swapped silently.
- Still no change to what serves live traffic.

**Phase 3 -- blue/green cutover (effort: medium-large; the only phase with
a deploy window).**
- Create a *new* Chroma collection (and, if Vectorize is active, a new
  Vectorize index) under a new name -- not a re-embed of the existing
  384-dim collection in place. The old collection is left standing,
  untouched, as the rollback target: reverting is "point config back at
  the old collection name," not "restore from backup."
- Re-ingest `occ_help` into the new collection via the Phase 2 provider.
  `seed_chroma.sh` is modified so an ingest failure during this migration
  is fail-loud in the sense Consequences below requires: a dimension or
  model mismatch must abort the boot path rather than leave
  `start_digisearch.sh` serving the old collection behind a WARN nobody
  reads (see the stale-serving bug above). Concretely, this means
  `start_digisearch.sh`'s `SEED_FAILED` branch stops being a warn-and-continue
  for this migration's cutover boot -- it must block startup until a human
  intervenes, distinct from routine reseed retries on unrelated content
  changes.
- If the Vectorize leg (`frontend/digithings-stack-cloudflare/container/entrypoint.sh`,
  `DIGI_VECTORIZE_ACTIVE` gate at lines ~52-71/79-84) is in active use for
  any deployed environment, it must be migrated to the new index in the
  same window or explicitly decommissioned in this ADR's follow-up PR --
  it cannot be left silently pointed at the old 384-dim index while Chroma
  moves on, or the two backends diverge.
- Cut traffic over only after Phase 0's gold eval set passes against the
  new collection with a defined, pre-agreed threshold (see Consequences:
  eval sign-off is an owner-approval item, not an engineering judgment
  call).
- This is the one phase that is not trivially revertible in the "revert
  the commit" sense: it involves a live cutover window, a new external
  Vectorize index if applicable, and a decision about how long the old
  collection is kept before deletion. Rollback is straightforward
  (point back at the old collection) but the *cutover itself* needs a
  scheduled window and sign-off, which is why Status is Proposed rather
  than Accepted.

**Phase 4 -- multilingual reranker, deferred, off by default (effort:
small, separately measured).**
- Swap `digisearch/src/digisearch/search/reranker.py`'s BGE code path from
  `BAAI/bge-reranker-base` (line 46, not multilingual) to
  `BAAI/bge-reranker-v2-m3` (multilingual). Note the *default* provider
  (`Reranker(provider="cohere")`, line 11) already calls Cohere's
  `rerank-multilingual-v3.0` (line 33), which is multilingual -- only the
  `bge` code path is mis-specified today.
  While touching this file, also fix the two bare `except Exception:
  return results[:n]` swallows (lines 39 and 54) to at least log at WARN;
  a reranker silently no-op'ing on every call is a second, unrelated
  silent-failure mode worth closing while the file is open, though it is
  not gating this ADR's rollout.
- Kept off by default and behind a flag, and deferred to its own PR
  measured independently of Phase 3, because a reranker can only reorder
  candidates the embedder already retrieved -- it is not load-bearing for
  the core defect this ADR addresses (see Context).

**Sequencing note:** `module/digisearch` is 11 commits behind `develop` as
of this writing (`git rev-list --count origin/module/digisearch..origin/develop`
= 11). Per the repo's branch-sync policy, this must be synced (a PR with
`head=develop` into `base=module/digisearch`) before cutting any
`task/<N>-slug` branch for Phase 1 onward -- cutting from the stale branch
today risks editing dead code, per the branching-model warning in the root
`CLAUDE.md`.

## Consequences

**Accepted tradeoffs:**
- Memory footprint roughly doubles for `occ_help` vectors: 768-dim
  (`gte-multilingual-base`) vs. 384-dim (Chroma's current default) per
  stored chunk. Accepted because the dimension change is also what makes a
  botched migration fail loudly (see disagreement 1) rather than silently
  mix models in one collection.
- No repo precedent exists for ONNX packaging of a non-bundled embedding
  model. The named fallback ladder (`gte-multilingual-base` ONNX ->
  `gte-multilingual-base` via `torch` -> `multilingual-e5-base` ->
  `e5-small` multilingual) exists specifically because this is unproven in
  this codebase; Phase 2's spike is timeboxed rather than open-ended for
  the same reason.
- No cross-lingual retrieval improvement ships to any user until Phase 3
  completes. Phases 0-2 are entirely prerequisite work with no observable
  effect on `occ_help` query results.
- `bge-m3` is deliberately not chosen now despite ranking well on quality;
  it is documented as a future upgrade path contingent on a keyword/BM25
  leg existing in production, which it does not today. Revisit only if a
  hybrid-retrieval leg is separately built.
- LLM query-translation (candidate C) remains available only as an
  optional, additive, flagged leg -- not part of the default path -- per
  disagreement 3.

**Requires explicit owner approval before implementation begins (Status:
Proposed, not Accepted, per the repo's human-gate policy for novel
architecture decisions):**
- This ADR itself.
- Container/instance sizing changes if the ONNX spike fails and `torch`
  becomes a runtime dependency -- a materially different resource profile
  than the current ONNX-only footprint.
- Provisioning the new Vectorize index, the corresponding
  `wrangler.toml` edit, and the Worker redeploy it implies, if the
  Vectorize leg is in active use in any deployed environment.
- The Phase 3 cutover window itself: downtime/degradation tolerance during
  re-ingest, and sign-off on the Phase 0 gold-eval threshold before
  traffic moves to the new collection. Neither is an engineering judgment
  call for a compliance corpus.
- Any use of a paid embedding or reranking API (OpenAI `text-embedding-3-small`,
  Cohere) for this corpus specifically -- an owner+legal decision, not an
  engineering default, because `occ_help` is a compliance corpus with no
  data-residency control once routed through a US third-party API. Nothing
  in this ADR requires a paid API; Phase 2's chosen model is self-hosted.
- Syncing `module/digisearch` against `develop` before any `task/<N>-slug`
  branch for this work is cut (11 commits behind as of this writing;
  re-check before branching, since the count moves).
