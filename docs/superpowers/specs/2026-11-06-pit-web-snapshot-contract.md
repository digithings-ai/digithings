# Point-in-time web snapshot contract

Status: contract. This document does not wire a backend. Exa Snapshot wiring is
[#29](https://github.com/digithings-ai/digithings/issues/29). The free Wayback
backend is [#28](https://github.com/digithings-ai/digithings/issues/28). Both
follow this contract. Parent epic:
[#30](https://github.com/digithings-ai/digithings/issues/30).

Exa facts below are from
[Exa Snapshot](https://exa.ai/docs/search/snapshot.md) as read on 2026-11-06.
If that page changes a limit or an error tag, the feat PR updates this
section in the same change.

Live web search with no `as_of` stays as it is today
(`digisearch/src/digisearch/web_exa.py`,
`digisearch/src/digisearch/web_search/`,
`digiquant/src/digiquant/research/data/web_grounding.py`). Monitors and
websets stay on the live path. Live-trading paths stay untouched.

## 1. Clock

`as_of` is the sim or run instant in UTC. Every web body, title, highlight,
summary, and author string a model can read must come from a stored page
version whose capture time is at or before that instant.

| Caller passes | Normalized `snapshot_as_of` |
|---|---|
| `YYYY-MM-DD` (a `run_date`) | `YYYY-MM-DDT23:59:59Z` |
| ISO-8601 instant with `Z` or a numeric offset | that instant, converted to UTC, whole seconds, `Z` suffix |

A date-only value is the sim day. End of that UTC day is the pin, so a
capture from the sim day stays eligible and a capture from the next UTC day
does not. Exa treats a bare date as midnight UTC. Callers send the
normalized instant. They do not send a bare date to Exa.

`as_of` later than the wall clock is `snapshot_rejected`. No request goes
out.

digiquant turns PIT mode on when the caller sets `as_of`, or when
`run_date` is strictly before today's UTC date. A `run_date` of today with
no explicit `as_of` stays on the live path. The existing grounding field
`as_of` remains the run-date label (`YYYY-MM-DD`). The pin is the separate
field `snapshot_as_of`.

## 2. What the model may read

In PIT mode the only web text that may enter `phase_inputs`, a prompt, or a
citation is text taken from an eligible snapshot body (title, text,
highlights, summary, author).

Discovery is allowed to run against the current index (see §4). The
discovery snippet and the discovery title are dropped on the floor. If the
snapshot fetch for that URL misses, the URL is dropped with them.

A fresh download of the original URL, including digifetch extract of the
live HTML, is not a snapshot.

## 3. Fail closed

Three caller-facing codes, same strings for Exa and Wayback:

| Code | When | digiquant `live_search` segment |
|---|---|---|
| `snapshot_missing` | The selected path answered, and no eligible capture exists for any kept URL | Evidence missing. `fetch_web_grounding` returns `evidence: []` and `snapshot_status: snapshot_missing`. It does not raise. No web body is copied into `phase_inputs`. The run continues. The analyst grades whatever evidence is left; the pipeline does not overwrite `data_quality`. |
| `snapshot_unavailable` | The chosen backend cannot serve (explicit `exa` with no key or a plan/trial 403; archive host down) | Segment fails (`DashboardWebSearchError`). |
| `snapshot_rejected` | Bad input: future `as_of`, snapshot combined with a live-web option, search type outside §7 | Segment fails. No request, or the request is not retried live. |

`snapshot_missing` is the coverage hole for the call: every kept URL
missed. One URL's `CONTENT_NOT_CACHED` drops that URL only;
`snapshot_status` stays `ok` when another URL still produced a row.
Multi-year archive coverage is sparse; a hole must not be filled with the
live page. Transport and configuration failures still fail the segment,
which is the rule `web_grounding.py` already uses for a broken search.

PIT mode never sends `livecrawl`, `livecrawlTimeout`, `maxAgeHours`, or
`subpages`, and never retries a miss as a live crawl.

## 4. Ranking honesty

Exa Search with `snapshotAsOf`, and SearXNG (or ddgs) followed by a
snapshot fetch, both discover URLs with **today's** index and then load a
historical body. Exa documents this: the cutoff bounds content, not
ranking. The free path has the same shape.

That result is evidence bounded by `snapshot_as_of`. It is not a replay of
the SERP a searcher would have seen on the sim day. Docs, diagnostics, and
eval notes say so in those words. Do not add a ranking-rewind flag that
claims otherwise.

Phase 1 of #28 may ship URL-known fetch first (contents-equivalent). Search
then snapshot is phase 2 and uses this same honesty rule.

## 5. Published-date filters and snapshot

`startPublishedDate` / `endPublishedDate` (and digisearch `recency_days`,
which maps onto them for Exa) select by the publisher's claimed publication
date. They do not pin which bytes of the page come back. A page published
inside the window can still be the 2026 revision of a 2019 article.

| Goal | Use |
|---|---|
| Live or current search for documents published in a window | `recency_days` or `startPublishedDate` / `endPublishedDate` |
| Bytes the model reads must be a version stored at or before T | `snapshot_as_of` |
| Both constraints at once | both, each doing only its own job |

A published-date filter on its own is not a point-in-time pin. PIT mode may
still send a published-date filter when the caller asked for one. It does
not replace the snapshot pin, and it does not relax §2.

## 6. Backend selection

`DIGISEARCH_SNAPSHOT_BACKEND=exa|wayback|auto`. Unset means `auto`. Read at
call time, same as `EXA_API_KEY`. Any other value is `snapshot_rejected`.

| Value | Behavior |
|---|---|
| `exa` | Exa only. Missing key, a plan/trial 403, or a window rejection is `snapshot_unavailable`. No Wayback retry. |
| `wayback` | Wayback only. Exa is not called. |
| `auto` | Exa when §7 says Exa is eligible; otherwise Wayback. A per-URL `CONTENT_NOT_CACHED` tries Wayback for that URL. The first plan/trial 403 in the process switches later calls in that process to Wayback. |

`auto` records the backend that actually produced each row. A silent switch
is allowed only in `auto`, and only along the paths in this table.

## 7. Exa limits, and when the house forces Wayback

Pay-as-you-go Snapshot, per the vendor page on 2026-11-06:

- Rolling 5-month index. An older `snapshotAsOf` is rejected.
- 10 QPS.
- 100 requests, then `403` `SNAPSHOT_TRIAL_EXHAUSTED` or
  `SNAPSHOT_TRIAL_CAP_EXCEEDED`.
- At most 10 search results, or 1 contents URL, per request.
- Free tier: `403` `SNAPSHOT_NOT_ON_PLAN`. Enterprise without the contract:
  `403` `SNAPSHOT_NOT_IN_CONTRACT`.
- Search `snapshotAsOf` sits under `contents`. Contents `snapshotAsOf` is
  top-level. The value is the normalized instant from §1.
- Allowed search types on this path: `auto`, `fast`, `instant`. `deep` and
  `deep-reasoning` are rejected by Exa. `deep-lite` and `lite` exist on some
  accounts; this contract does not send them.
- Combining `snapshotAsOf` with `livecrawl`, `livecrawlTimeout`,
  `maxAgeHours`, or `subpages` is `INVALID_REQUEST`. Omit those fields.
- A URL with no eligible version is omitted from `results`. `statuses[]`
  reports `status: error` and `error.tag: CONTENT_NOT_CACHED`. That tag is
  `snapshot_missing` for that URL. It is not a cue to live-fetch.

House policy:

- Pace Exa snapshot calls at or below 10 QPS. Cap search `numResults` at 10
  and contents at one URL.
- `effort=thorough` on the live Exa path maps to `deep`. On the snapshot
  path `thorough` sends `type=auto`. `fast` sends `fast`. Unset sends
  `auto`.
- Client-side window check: if the normalized instant's UTC date is strictly
  earlier than the request's UTC date minus five calendar months, `auto`
  uses Wayback and does not call Exa. Example: a request on 2026-11-06 skips
  Exa for an `as_of` before 2026-06-06. Exa's own rejection remains
  authoritative; in `auto` that rejection also falls through to Wayback.
- A multi-year backtest sets `DIGISEARCH_SNAPSHOT_BACKEND=wayback` up front
  so the 100-request trial is not spent discovering the wall. `auto` is for
  a run whose `as_of` sits inside the window and whose call count fits in
  the remaining trial.
- Explicit `exa` outside the window, or after a trial/plan 403, fails with
  `snapshot_unavailable`. It does not quietly become Wayback.

Wayback (#28) resolves the newest capture with timestamp `<= snapshot_as_of`
via the Internet Archive Availability API and CDX. Memento TimeGate is
optional. Fetch `https://web.archive.org/web/{timestamp}id_/{url}` (`id_` is
the raw capture, toolbar stripped) through digifetch, and only after the
URL has been rewritten to an allow-listed archive host. A CDX row later than
`snapshot_as_of` is ignored even if the API returned it. One process sends
at most one archive.org request per second and caches the CDX listing for
the run. That cap is politeness toward the archive. It is not Exa's 10 QPS.

`snapshot_backend` is `exa` or `wayback`. A TimeGate win on a host other
than `web.archive.org` still stamps `wayback` until a later issue adds a
third backend.

## 8. Evidence shape

PIT mode adds `evidence` beside the existing grounding dict. `summary` is
built only from `evidence` title and text. `sources` stays a list of
original URL strings, same order as `evidence`, so current URL consumers
keep working.

```json
{
  "summary": "- [Snapshot title](https://example.com/story): body from the capture",
  "sources": ["https://example.com/story"],
  "as_of": "2019-06-01",
  "snapshot_status": "ok",
  "evidence": [
    {
      "url": "https://example.com/story",
      "snapshot_backend": "wayback",
      "snapshot_as_of": "2019-06-01T23:59:59Z",
      "captured_at": "2019-05-28T11:04:02Z",
      "archive_url": "https://web.archive.org/web/20190528110402id_/https://example.com/story"
    }
  ]
}
```

`snapshot_status` is `ok` when `evidence` has a row, and `snapshot_missing` when the coverage hole from §3 leaves it empty. `summary` is an empty string in that case, which is legal only together with `snapshot_status: snapshot_missing`. Live mode still rejects an empty summary.

`archive_url` is required for `wayback` and null for `exa`. `captured_at`
is the CDX timestamp for Wayback. Exa often omits a version timestamp;
`captured_at` is then null, and only because the request carried
`snapshotAsOf` and the status was a cached success. A null `captured_at`
does not permit a live body.

Live mode omits `evidence`.

## 9. Telemetry

Stamp the three fields on every evidence item (§8) and once on the research
diagnostics row the olympus daily thesis already reads:
`run_diagnostics.breakdown.web_snapshot`
(`digiquant/src/digiquant/research/diagnostics.py`). No new table.

```json
{
  "snapshot_backend": ["wayback"],
  "snapshot_as_of": "2019-06-01T23:59:59Z",
  "captures": 1,
  "misses": 0
}
```

`snapshot_backend` is the distinct backends that produced a row.
`snapshot_as_of` is the run's normalized instant. `captures` counts
evidence items with a non-null `captured_at`. `misses` counts
`snapshot_missing` URLs. Page bodies stay out of the diagnostics row.

Names in prose stay lowercase (`digisearch`, `digiquant`, `digigraph`).

## 10. Test plan

The feat PRs add this fixture. This spec PR does not.

Golden page, no network. The capture at `2019-05-28T11:04:02Z` contains the
string `PIT_PRE_T_MARKER` and does not contain `PIT_POST_T_MARKER`. The live
body contains `PIT_POST_T_MARKER` and does not contain `PIT_PRE_T_MARKER`.
`run_date` / `as_of` is `2019-06-01`.

Assert all of the following on the grounding dict and on the text that would
enter the model prompt:

1. `PIT_PRE_T_MARKER` is present.
2. `PIT_POST_T_MARKER` is absent, including inside a discovery snippet.
3. The Exa JSON has `snapshotAsOf` set to `2019-06-01T23:59:59Z` (under
   `contents` for search, top-level for contents) and has no `livecrawl`,
   `livecrawlTimeout`, `maxAgeHours`, or `subpages`.
4. `type` is `auto`, `fast`, or `instant`. `effort=thorough` still sends
   `auto`.
5. A mock `CONTENT_NOT_CACHED` plus a Wayback miss yields
   `snapshot_status: snapshot_missing`, an empty `evidence` list, an empty
   `summary`, and still no `PIT_POST_T_MARKER`. The call does not raise.
6. A CDX row at `2019-06-02T00:00:01Z` is not selected.
7. `evidence[0]` and `breakdown.web_snapshot` carry `snapshot_backend`,
   `snapshot_as_of`, and `captured_at` as in §8 and §9.

## 11. Checklist

### #29 — Exa Snapshot

- [ ] `snapshot_as_of` on `exa_search` and the contents helper. Search puts
      `snapshotAsOf` under `contents`. Contents puts it top-level.
- [ ] Omit `livecrawl`, `livecrawlTimeout`, `maxAgeHours`, `subpages` when
      the pin is set. Reject `deep` and `deep-reasoning`. Map
      `effort=thorough` to `auto` on this path.
- [ ] Surface `CONTENT_NOT_CACHED` as `snapshot_missing` for that URL.
- [ ] Honor 10 QPS, 10 search results, one contents URL, and the 403 tags in
      §7.
- [ ] Orchestrator and MCP `web_search` accept `as_of` and forward it.
      digigraph does not drop the field.
- [ ] digiquant historical `run_date` passes the normalized instant.
      Today's run without `as_of` stays live.
- [ ] Unit tests for the payload, the rejected combinations, and §10.

### #28 — Wayback

- [ ] `resolve` returns the newest capture `<= snapshot_as_of`, or none.
- [ ] Fetch the `id_` raw URL through digifetch. Allow-list archive hosts
      only. The original URL is not fetched while PIT mode is on.
- [ ] A miss is `snapshot_missing`, with no live HTML and no empty string
      pretending to be a body.
- [ ] Same `evidence` object and the same three telemetry fields.
- [ ] At most one archive.org request per second per process; cache the CDX
      listing for the run.
- [ ] Phase 1 is URL-known fetch. Phase 2 is search-then-snapshot, with §4
      stated in the module doc.
- [ ] The §10 fixture passes on this backend too.

### Both

- [ ] Read `DIGISEARCH_SNAPSHOT_BACKEND` as in §6.
- [ ] When #29 edits `digisearch/ARCHITECTURE.md`, add a short pointer at this
      file in the same change. That edit regenerates the chunker fingerprint
      in `tests/ds/test_chunkers.py`; a pointer-only edit here would do that
      twice. The digiquant pointer already lives in `digiquant/AGENTS.md`
      (section "PIT web snapshot").
      `digiquant/src/digiquant/research/docs/RUNBOOK.md` is not in the tree;
      do not invent that file to hold the pointer.
- [ ] State §4 in the operator note next to the flag.

## 12. Out of scope

- Building either backend in the spec PR.
- Replaying a historical SERP.
- Common Crawl, or a self-hosted crawler.
- A new digikey scope. Snapshot rides the existing `digisearch:query` path.
- Turning snapshot on for monitors or websets.
- Any change under `digiquant/live/`, `digiquant/brokers/`, or `config/live*`.
