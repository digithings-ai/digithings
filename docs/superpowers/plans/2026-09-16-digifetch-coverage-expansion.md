# digifetch coverage expansion (phase 4a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the two residual #4110 endpoints — a detail mode on `digifetch_transcripts` (`GET /cloud/transcripts/{id}`) and the new `digifetch_saved_searches` tool (`GET /cloud/search/saved`) — on every registration surface (models, normalizers, client, entitlements, MCP, orchestrator manifest, in-process dispatcher), TDD and offline-tested.

**Architecture:** Extend the shipped Gloomberb Cloud client in `digiquant/src/digiquant/data/gloomberb/` following approach (c) of the #3927 scoping spec. Detail routes of the same resource fold into the existing tool (the `digifetch_news.story_id` precedent); a distinct resource gets a new tool. One shared `GloomberbClient` keeps pacing/cache/breaker for MCP and pipeline callers; every call returns `DigifetchEnvelope[T]` and never raises.

**Tech Stack:** Python 3.12, Pydantic v2 (`_InputModel` extra="forbid", `_CamelModel` extras preserved), `httpx.MockTransport` behind `digifetch.HttpFetcher` for offline tests, FastMCP wrappers, pytest `-m unit`, ruff line length 100, Polars-only repo rule (no pandas anywhere in this plan).

**Spec:** `docs/superpowers/specs/2026-09-16-digifetch-coverage-expansion-design.md` — the plan argues from the spec; executors read both. #4110's issue body is stale: phases 1-3 shipped (#4112/#4119/#4126, entitlements #4135); this plan covers phase 4a only.

## Global Constraints

- **Issue / branch discipline:** cut `task/4110-*` with `make task ISSUE=4110` from a fresh `module/digiquant` (the script fetches `origin` and refuses a stale module base); PR base is `module/digiquant`. The PR **advances** #4110 (phase 4a) — do **not** put `Fixes #4110` in the body, because phases 4b/4c (plugin panes, surface integration) stay open in that issue. Reference it as `Advances #4110`.
- **Read-only + enrichment-only:** both tools are read-scope; nothing is persisted anywhere (the platform stores the data). Both are registered in `READ_SCOPE_TOOLS` and never gain write/mutating behavior.
- **NFR numbers (current code, spec §5):** 900 s TTL cache (`client.py:161`), 0.5 s min request interval (`client.py:158`), circuit breaker 3 consecutive upstream failures / 60 s reset (`client.py:162-163`), 256-entry cache bound (`client.py:168`), 429 `Retry-After` honored only up to 5.0 s (`client.py:166`), kill switch `GLOOMBERB_ENABLED` default ON with only `1/true/yes/on` enabling (`client.py:248-272`). Do not invent new pacing values; the new methods inherit the client-wide ones.
- **Human gate:** none for this PR — `api.gloom.sh` already shipped (#4085). The one true gate: **do not add a non-gloomberb external dependency**. If a task seems to need one, stop and file a new issue + human gate; do not implement it here.
- **Session cookie:** `GLOOMBERB_SESSION_COOKIE` (bare token or `name=value`; runbook #4099) is forwarded only to `gated=True` requests; never logged, never a tool input.
- **Probe-first:** the detail shapes are unverified; wire types stay permissive (`str | int` ids, optional fields, extras preserved) until the Task 1 probe records the live payloads. Do not tighten a permissive wire type without a probe.
- **Cross-references:** #4069/#4085 (origin contract), #4098 (surface integration, out of scope here), #4101 (post-deploy verification), #4099 (cookie runbook), #4100 (history-window escape hatch — untouched).
- **Naming:** every product/module name is lowercase `digi*` in prose, commits, and PR text (`digifetch`, `digiquant`, `gloomberb`). Tool names follow the shipped `digifetch_*` convention.
- **Tests never hit the live API:** `httpx.MockTransport` on an injected `digifetch.HttpFetcher`, or a patched `_build_gloomberb_client`. The only live commands are the Task 1 probes.
- **Review + merge:** per `AGENTS.md` merge-when-ready — required CI green, review coverage on the record (`/review`, in-session findings comment + `reviewed:agent`), then merge into `module/digiquant`.

---

### Task 1: Branch, live probes, contract freeze

**Files:**
- Modify: `docs/superpowers/specs/2026-09-16-digifetch-coverage-expansion-design.md` (§11 probe record; §4/§6 rows only if a probe contradicts them)

**Interfaces:**
- Consumes: live `https://api.gloom.sh` + a `GLOOMBERB_SESSION_COOKIE` from the #4099 runbook (Pro account needed for the transcripts probe); `make task`.
- Produces: a recorded go/no-go and the exact payload shapes Tasks 2-5 model; branch `task/4110-*`.

- [ ] **Step 1: Cut the branch**

Run:
```bash
gh issue view 4110 -R digithings-ai/digithings --json state,title
make task ISSUE=4110
```
Expected: issue `OPEN`; a worktree on `task/4110-<slug>` cut from `refs/remotes/origin/module/digiquant`, with the module base not stale (the script refuses otherwise).

- [ ] **Step 2: Probe the transcripts list route (Pro session)**

Run (never echo the cookie value; `-b` reads the env var):
```bash
test -n "$GLOOMBERB_SESSION_COOKIE" || echo "NO COOKIE — use the #4099 runbook, or record a free-session 402 below"
curl -sS -o /tmp/digifetch-transcripts-list.json -w '%{http_code}\n' \
  -H 'Accept: application/json' -b "$GLOOMBERB_SESSION_COOKIE" \
  'https://api.gloom.sh/cloud/transcripts?ticker=AAPL&limit=1'
python -c "import json;d=json.load(open('/tmp/digifetch-transcripts-list.json'));print(json.dumps(d,indent=2)[:1200])"
```
Expected: `200` for a Pro session; the payload wraps rows under `calls` with an `id` per row. Record the exact key path. A `402`/text `Pro plan required` means the session is not Pro: record that and skip Step 3 (the go/no-go in Step 5 still allows Task 2-5 with the probe-pending marker).

- [ ] **Step 3: Probe the transcripts detail route**

Extract the id from Step 2 and fetch it:
```bash
TRANSCRIPT_ID=$(python -c "import json;d=json.load(open('/tmp/digifetch-transcripts-list.json'));print((d.get('calls') or d.get('transcripts') or [{}])[0].get('id',''))")
echo "$TRANSCRIPT_ID"
curl -sS -o /tmp/digifetch-transcript-detail.json -w '%{http_code}\n' \
  -H 'Accept: application/json' -b "$GLOOMBERB_SESSION_COOKIE" \
  "https://api.gloom.sh/cloud/transcripts/$TRANSCRIPT_ID"
python -c "import json;d=json.load(open('/tmp/digifetch-transcript-detail.json'));print(type(d).__name__);print(json.dumps(d,indent=2)[:2000])"
```
Record: status; top-level type (object vs array); whether the row is bare or wrapped in `transcript`; whether `id`/`ticker`/`companyName`/`callAt` are present; where the transcript body lives (extras are fine — it must not be dropped).

- [ ] **Step 4: Probe the saved-searches route**

```bash
curl -sS -o /tmp/digifetch-saved-searches.json -w '%{http_code}\n' \
  -H 'Accept: application/json' -b "$GLOOMBERB_SESSION_COOKIE" \
  'https://api.gloom.sh/cloud/search/saved'
python -c "import json;d=json.load(open('/tmp/digifetch-saved-searches.json'));print(type(d).__name__);print(json.dumps(d,indent=2)[:2000])"
```
Record: status; bare array vs `{searches: [...]}` / other key; row fields. A `401` without a cookie is expected; a `402`/Pro body means the spec's `session` entitlement row becomes `pro` (amend §4/§6 before Task 5).

- [ ] **Step 5: Record the probe outcomes in the spec (go/no-go)**

Edit `docs/superpowers/specs/2026-09-16-digifetch-coverage-expansion-design.md` §11:

- Replace open questions 1-3 with the observed facts (status, shape, wrapped/bare, id presence, Pro-vs-session).
- **Go** if both routes answered `200` (or `402` for a free session on transcripts, in which case mark both transcript shapes `probe-pending (free session; Pro-account probe outstanding)` and keep the permissive models);
- **No-go** if either route answers `404`/`405` or is absent: delete the corresponding tool from §4/§6, add a one-line note, close this plan task without implementation, and comment on #4110 that the endpoint is gone.
- If the saved-searches route is Pro-gated, change its entitlement in §4/§6 from `session` to `pro`.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-09-16-digifetch-coverage-expansion-design.md
git commit -m "docs(digiquant): record digifetch phase-4a endpoint probes (#4110)"
```

---

### Task 2: `digifetch_transcripts` detail input + normalizer

**Files:**
- Modify: `digiquant/src/digiquant/data/gloomberb/models.py:611-613` (`TranscriptsInput`), and the `__all__` list at the top of the module (add `TranscriptId`)
- Modify: `digiquant/src/digiquant/data/gloomberb/normalizers.py` (add after `normalize_transcripts`, ~`:1023`)
- Modify: `digiquant/src/digiquant/data/gloomberb/__init__.py` (export `TranscriptId` if the module's convention is to re-export; the existing `TranscriptsInput`/`Transcript` are re-exported there)
- Test: `tests/dq/data/test_gloomberb_models.py`, `tests/dq/data/test_gloomberb_normalizers.py`

**Interfaces:**
- Consumes: `Symbol`, `_InputModel`, `Transcript`, `_rows`.
- Produces: `TranscriptId` (Annotated str, 1-200); `TranscriptsInput(ticker: Symbol | None = None, transcript_id: TranscriptId | None = None, limit: int = 20)` with exactly one target enforced; `normalize_transcript_detail(raw: Any, fallback_id: str) -> Transcript` — used by Task 3.

- [ ] **Step 1: Write the failing model test**

Append to `tests/dq/data/test_gloomberb_models.py`:

```python
# ── coverage-expansion input bounds (#4110 phase 4a) ─────────────────────────


def test_transcripts_accepts_exactly_one_target() -> None:
    assert TranscriptsInput(ticker="AAPL").transcript_id is None
    assert TranscriptsInput(transcript_id="t1").ticker is None
    with pytest.raises(ValidationError):
        TranscriptsInput()
    with pytest.raises(ValidationError):
        TranscriptsInput(ticker="AAPL", transcript_id="t1")
    with pytest.raises(ValidationError):
        TranscriptsInput(transcript_id="x" * 201)
    assert TranscriptsInput(ticker="AAPL", limit=100).limit == 100
    with pytest.raises(ValidationError):
        TranscriptsInput(ticker="AAPL", limit=101)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/dq/data/test_gloomberb_models.py::test_transcripts_accepts_exactly_one_target -v`
Expected: FAIL — `AttributeError: 'TranscriptsInput' object has no attribute 'transcript_id'` (or a `ValidationError` on the second line: `ticker` is currently required and unknown fields are forbidden).

- [ ] **Step 3: Write the minimal implementation**

In `models.py`, replace the `TranscriptsInput` block (`:611-613`) with:

```python
#: One transcript id from a `digifetch_transcripts` list row
#: (`/cloud/transcripts/{id}`; probe-pending shape, so the bound is generous).
TranscriptId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class TranscriptsInput(_InputModel):
    """List one ticker's calls, or fetch one call by id (exactly one target).

    `ticker` selects ``GET /cloud/transcripts``; `transcript_id` (from a list
    row) selects ``GET /cloud/transcripts/{id}``. Both routes are session-gated
    and require a Gloomberb Pro plan.
    """

    ticker: Symbol | None = None
    transcript_id: TranscriptId | None = None
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "TranscriptsInput":
        if (self.ticker is None) == (self.transcript_id is None):
            raise ValueError("provide exactly one of ticker or transcript_id")
        return self
```

Add `"TranscriptId",` to the module `__all__` (alphabetical position near `"Transcript"`/`"TranscriptsEnvelope"`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/dq/data/test_gloomberb_models.py::test_transcripts_accepts_exactly_one_target tests/dq/data/test_gloomberb_models.py -q`
Expected: PASS, including the pre-existing `test_new_tool_limits_are_bounded` (which calls `TranscriptsInput(ticker="aapl", limit=100)`).

- [ ] **Step 5: Write the failing normalizer test**

Add `normalize_transcript_detail` to the import block at the top of `tests/dq/data/test_gloomberb_normalizers.py` (alphabetical position after `normalize_transcripts`), then append:

```python
def test_normalize_transcript_detail_accepts_wrapped_bare_and_fallback_id() -> None:
    wrapped = {
        "transcript": {"id": "t1", "companyName": "Apple Inc.", "callAt": "2026-08-01T16:30:00Z"}
    }
    row = normalize_transcript_detail(wrapped, "t1")
    assert row.id == "t1"
    assert row.company_name == "Apple Inc."
    assert row.call_at == "2026-08-01T16:30:00Z"

    bare = normalize_transcript_detail({"companyName": "Apple Inc."}, "t9")
    assert bare.id == "t9"

    assert normalize_transcript_detail("not-a-mapping", "t2").id == "t2"

    extra = normalize_transcript_detail({"id": "t3", "segments": [{"speaker": "Tim"}]}, "t3")
    assert extra.model_dump()["segments"] == [{"speaker": "Tim"}]
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `pytest tests/dq/data/test_gloomberb_normalizers.py::test_normalize_transcript_detail_accepts_wrapped_bare_and_fallback_id -v`
Expected: FAIL — `ImportError: cannot import name 'normalize_transcript_detail' from 'digiquant.data.gloomberb.normalizers'`.

- [ ] **Step 7: Write the minimal implementation**

In `normalizers.py`, immediately after `normalize_transcripts` (~`:1023`), add:

```python
def normalize_transcript_detail(raw: Any, fallback_id: str) -> Transcript:
    """Map ``/cloud/transcripts/{id}`` to one row (shape probe-pending).

    Accepts a wrapped ``{"transcript": {...}}`` or a bare object; the requested
    id supplies ``id`` when the payload omits it and a non-mapping payload
    (unexpected wire shape) still yields a typed row. Unknown fields — the
    transcript body included — stay extras; nothing is dropped.
    """
    payload: Any = raw
    if isinstance(raw, Mapping) and isinstance(raw.get("transcript"), Mapping):
        payload = raw["transcript"]
    merged: dict[str, Any] = dict(payload) if isinstance(payload, Mapping) else {}
    merged.setdefault("id", fallback_id)
    return Transcript.model_validate(merged)
```

- [ ] **Step 8: Run both test files to verify they pass**

Run: `pytest tests/dq/data/test_gloomberb_models.py tests/dq/data/test_gloomberb_normalizers.py -m unit -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add digiquant/src/digiquant/data/gloomberb/models.py digiquant/src/digiquant/data/gloomberb/normalizers.py digiquant/src/digiquant/data/gloomberb/__init__.py tests/dq/data/test_gloomberb_models.py tests/dq/data/test_gloomberb_normalizers.py
git commit -m "feat(digiquant): transcripts detail input model and normalizer (#4110)"
```

---

### Task 3: `digifetch_transcripts` detail client path + MCP/manifest surfaces

**Files:**
- Modify: `digiquant/src/digiquant/data/gloomberb/client.py:1358-1408` (`transcripts`)
- Modify: `digiquant/src/digiquant/mcp_server.py:1236-1249` (`digifetch_transcripts` wrapper)
- Modify: `digiquant/src/digiquant/orchestrator_tools.py:666-687` (`build_digifetch_transcripts_tool`)
- Test: `tests/dq/data/test_gloomberb_client.py`, `tests/dq/test_mcp_gloomberb_tools.py`

**Interfaces:**
- Consumes: `TranscriptsInput` + `normalize_transcript_detail` (Task 2); `ENDPOINTS["transcripts"]`, `quote`, `_request_json`, `_data_or_error`, `_normalize`, `_freshness`, `_rows_stale`, `_cached`.
- Produces: `GloomberbClient.transcripts` handles both modes; MCP wrapper signature `digifetch_transcripts(ticker: str | None = None, limit: int = 20, transcript_id: str | None = None) -> str`; manifest parameters gain `transcript_id` and drop `required` (both targets optional at the schema level; the model still rejects neither/both).

- [ ] **Step 1: Write the failing client tests**

Append to `tests/dq/data/test_gloomberb_client.py` (fixtures `make_client` and `clean_env` already exist):

```python
def test_transcripts_detail_mode_fetches_by_id_and_requires_pro() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "transcript": {
                    "companyName": "Apple Inc.",
                    "callAt": "2026-08-01T16:30:00Z",
                }
            },
        )

    denied = make_client(handler).transcripts({"transcript_id": "t1"})
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert seen == {}

    allowed = make_client(handler, session_cookie="token").transcripts({"transcript_id": "t1"})
    assert seen["path"] == "/cloud/transcripts/t1"
    row = allowed.data.transcripts[0]  # type: ignore[union-attr]
    assert row.id == "t1"
    assert row.company_name == "Apple Inc."


def test_transcripts_rejects_two_targets_before_any_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"calls": []})

    result = make_client(handler, session_cookie="token").transcripts(
        {"ticker": "AAPL", "transcript_id": "t1"}
    )
    assert result.data.code == "invalid_input"  # type: ignore[union-attr]
    assert calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/dq/data/test_gloomberb_client.py::test_transcripts_detail_mode_fetches_by_id_and_requires_pro tests/dq/data/test_gloomberb_client.py::test_transcripts_rejects_two_targets_before_any_request -v`
Expected: first FAIL — `AssertionError: assert '/cloud/transcripts' == '/cloud/transcripts/t1'` (the current method always calls the list route); second PASS (the Task 2 model validator already rejects two targets). Proceed because the deliverable is the pair.

- [ ] **Step 3: Write the minimal implementation**

In `client.py`, replace the body of `produce()` inside `transcripts` (`:1371-1406`) with the two-mode version:

```python
        def produce() -> TranscriptsEnvelope:
            if parsed.transcript_id:
                path = f"{ENDPOINTS['transcripts']}/{quote(parsed.transcript_id, safe='')}"
                raw = self._request_json("GET", path, gated=True, pro_gated=True)
            else:
                raw = self._request_json(
                    "GET",
                    ENDPOINTS["transcripts"],
                    params={"ticker": parsed.ticker, "limit": str(parsed.limit)},
                    gated=True,
                    pro_gated=True,
                )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(TranscriptsEnvelope, raw)
            result = self._data_or_error(raw, "Cloud transcripts are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(TranscriptsEnvelope, result)
            data, warnings = result
            if parsed.transcript_id:
                row = self._normalize(
                    nz.normalize_transcript_detail, data, parsed.transcript_id
                )
                if isinstance(row, DigifetchError):
                    return self._error_envelope(TranscriptsEnvelope, row)
                rows = [row]
                list_rows: Any = data
            else:
                rows = self._normalize(nz.normalize_transcripts, data)
                if isinstance(rows, DigifetchError):
                    return self._error_envelope(TranscriptsEnvelope, rows)
                # The live list payload wraps its rows under `calls`; `transcripts`
                # is accepted for a wrapped variant.
                list_rows = (
                    (data.get("calls") or data.get("transcripts"))
                    if isinstance(data, Mapping)
                    else data
                )
            fresh = self._freshness(raw, data, extra_stale=self._rows_stale(list_rows))
            return TranscriptsEnvelope(
                data=TranscriptsResult(transcripts=rows),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )
```

`quote` is already imported (`client.py:31`); no new imports.

- [ ] **Step 4: Run the client tests to verify they pass**

Run: `pytest tests/dq/data/test_gloomberb_client.py -m unit -q -k "transcript"`
Expected: PASS, including the pre-existing list-mode and `pro_required` tests.

- [ ] **Step 5: Write the failing MCP wrapper test**

Append to `tests/dq/test_mcp_gloomberb_tools.py`:

```python
def test_transcripts_detail_mode_maps_the_wrapped_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cloud/transcripts/t1"
        return httpx.Response(200, json={"companyName": "Apple Inc."})

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_transcripts")(None, 20, "t1"))
    row = payload["data"]["transcripts"][0]
    assert row["id"] == "t1"
    assert row["company_name"] == "Apple Inc."
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION
    assert "source_url" not in payload
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `pytest tests/dq/test_mcp_gloomberb_tools.py::test_transcripts_detail_mode_maps_the_wrapped_payload -v`
Expected: FAIL — `TypeError` (wrong arity): the current wrapper is `digifetch_transcripts(ticker, limit)` while the test calls `_mcp("digifetch_transcripts")` with three positional args (`None, 20, "t1"`), so the call never reaches the model.

- [ ] **Step 7: Write the minimal implementation (wrapper + manifest)**

Replace the wrapper in `mcp_server.py` (`:1236-1249`) with:

```python
    @_maybe_tool("digifetch_transcripts")
    def digifetch_transcripts(
        ticker: str | None = None,
        limit: int = 20,
        transcript_id: str | None = None,
    ) -> str:
        """Earnings-call transcripts (Gloomberb Cloud; session-gated, requires Pro).

        Two modes; provide exactly one target. `ticker` lists that listing's
        calls; `transcript_id` (from a list row) fetches one call's detail.
        Requires GLOOMBERB_SESSION_COOKIE **and** a Gloomberb Pro plan: a free
        (email-verified) session answers a "Pro plan required" body, mapped to
        a typed `pro_required` with the upstream text - never an empty
        success. List mode carries a term.gloom.sh deep link for `ticker`;
        detail mode has no link unless `ticker` is known from the payload.
        """
        try:
            envelope = _build_gloomberb_client().transcripts(
                {"ticker": ticker, "limit": limit, "transcript_id": transcript_id}
            )
        except Exception as exc:  # surface as JSON to the caller, never crash
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        # Detail mode has no ticker argument, but the row can carry one — the
        # spec's "or the payload carries one" deep-link rule.
        symbol = ticker
        if symbol is None:
            rows = getattr(envelope.data, "transcripts", None) or []
            symbol = rows[0].ticker if rows else None
        return _gloomberb_envelope_json(envelope, symbol=symbol)
```

Update `build_digifetch_transcripts_tool` in `orchestrator_tools.py` (`:666-687`): add `transcript_id` to `properties` and delete the `"required": ["ticker"]` line (neither target is schema-required; the Pydantic validator enforces exactly-one):

```python
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                    "transcript_id": {"type": "string"},
                },
            },
```

Also extend the builder description with: `"ticker lists a listing's calls; transcript_id (from a list row) fetches one call's detail — provide exactly one."`

- [ ] **Step 8: Run the wiring tests to verify they pass**

Run:
```bash
pytest tests/dq/test_mcp_gloomberb_tools.py -m unit -q -k "transcript"
pytest tests/dq/data/test_gloomberb_agent_tools.py -m unit -q
```
Expected: PASS. The parity test `test_dispatch_table_covers_every_schema_and_matches_its_parameters` requires manifest `properties` == model fields and `required` == model-required fields, so the manifest edit above is mandatory.

- [ ] **Step 9: Commit**

```bash
git add digiquant/src/digiquant/data/gloomberb/client.py digiquant/src/digiquant/mcp_server.py digiquant/src/digiquant/orchestrator_tools.py tests/dq/data/test_gloomberb_client.py tests/dq/test_mcp_gloomberb_tools.py
git commit -m "feat(digiquant): transcripts-by-id detail path in MCP and manifest (#4110)"
```

---

### Task 4: `digifetch_saved_searches` models + normalizer

**Files:**
- Modify: `digiquant/src/digiquant/data/gloomberb/models.py` (input after `VenuesInput` `:644-645`; payload after `VenuesResult` `~:1504-1508`; envelope alias after `VenuesEnvelope` `:1992`; module `__all__`)
- Modify: `digiquant/src/digiquant/data/gloomberb/normalizers.py` (after `normalize_venues` `~:1119`)
- Modify: `digiquant/src/digiquant/data/gloomberb/__init__.py` (imports + `__all__`)
- Test: `tests/dq/data/test_gloomberb_models.py`, `tests/dq/data/test_gloomberb_normalizers.py`

**Interfaces:**
- Consumes: `_InputModel`, `_CamelModel`, `DigifetchEnvelope`, `_rows`.
- Produces: `SavedSearchesInput` (parameterless), `SavedSearch` (permissive row), `SavedSearchesResult(searches: list[SavedSearch])`, `SavedSearchesEnvelope`; `normalize_saved_searches(raw: Any) -> SavedSearchesResult` — used by Task 5.

- [ ] **Step 1: Write the failing model test**

Append to `tests/dq/data/test_gloomberb_models.py`:

```python
def test_saved_searches_models_are_parameterless_and_permissive() -> None:
    assert SavedSearchesInput().model_dump() == {}
    with pytest.raises(ValidationError):
        SavedSearchesInput(limit=5)  # type: ignore[call-arg]

    row = SavedSearch(
        id="s1", name="AI capex", query="AI capex", created_at="2026-09-01T00:00:00Z"
    )
    assert row.name == "AI capex"
    assert row.query == "AI capex"
    result = SavedSearchesResult(searches=[row])
    assert result.searches[0].id == "s1"
    # Extras stay available (the live row shape is probe-pending).
    extra = SavedSearch(id="s2", pinned=True)
    assert extra.model_dump()["pinned"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/dq/data/test_gloomberb_models.py::test_saved_searches_models_are_parameterless_and_permissive -v`
Expected: FAIL — `ImportError: cannot import name 'SavedSearchesInput' from 'digiquant.data.gloomberb.models'`.

- [ ] **Step 3: Write the minimal implementation**

In `models.py`, after `VenuesInput` (`:644-645`), add:

```python
class SavedSearchesInput(_InputModel):
    """The Cloud saved-searches route takes no parameters."""
```

After `VenuesResult` (find it near `:1504`), add:

```python
class SavedSearch(_CamelModel):
    """One saved-search row from ``/cloud/search/saved`` (shape probe-pending).

    The live row shape is unverified; the common fields are typed optionally
    and unknown fields stay extras until the Task 1 probe records the payload.
    """

    id: str | int | None = None
    name: str | None = None
    query: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SavedSearchesResult(_CamelModel):
    searches: list[SavedSearch] = Field(default_factory=list)
```

After `VenuesEnvelope` (`:1992`), add:

```python
SavedSearchesEnvelope = DigifetchEnvelope[SavedSearchesResult]
```

Add the four names to the module `__all__` (alphabetical, near `"SavedSearch"`/`"SearchEnvelope"`), and the same names to the imports + `__all__` in `__init__.py` (next to `SearchEnvelope`/`SearchInput`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/dq/data/test_gloomberb_models.py -m unit -q -k "saved_searches"`
Expected: PASS.

- [ ] **Step 5: Write the failing normalizer test**

Add `normalize_saved_searches` to the import block of `tests/dq/data/test_gloomberb_normalizers.py` (after `normalize_research_search`), then append:

```python
def test_normalize_saved_searches_accepts_wrapped_and_bare_shapes() -> None:
    wrapped = {"searches": [{"id": "s1", "name": "AI capex", "query": "AI capex"}]}
    rows = normalize_saved_searches(wrapped)
    assert rows.searches[0].id == "s1"
    assert rows.searches[0].name == "AI capex"

    bare = [{"id": "s2", "query": "rates"}]
    assert normalize_saved_searches(bare).searches[0].query == "rates"

    assert normalize_saved_searches({"saved": []}).searches == []
    assert normalize_saved_searches(None).searches == []
    extra = normalize_saved_searches({"searches": [{"id": "s3", "pinned": True}]})
    assert extra.searches[0].model_dump()["pinned"] is True
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `pytest tests/dq/data/test_gloomberb_normalizers.py::test_normalize_saved_searches_accepts_wrapped_and_bare_shapes -v`
Expected: FAIL — `ImportError: cannot import name 'normalize_saved_searches'`.

- [ ] **Step 7: Write the minimal implementation**

In `normalizers.py`, after `normalize_venues` (`~:1119`), add:

```python
def normalize_saved_searches(raw: Any) -> SavedSearchesResult:
    """Map ``/cloud/search/saved`` rows (bare array or a wrapped key).

    The live key is probe-pending: ``searches`` is the primary shape and
    ``saved`` is accepted as a fallback until the Task 1 probe records it.
    Unknown row fields stay extras.
    """
    payload: Any = raw
    if isinstance(raw, Mapping):
        payload = raw.get("searches") or raw.get("saved")
    return SavedSearchesResult(
        searches=[SavedSearch.model_validate(dict(entry)) for entry in _rows(payload, "searches")]
    )
```

Add `SavedSearch`/`SavedSearchesResult` to the imports from `.models` in `normalizers.py`.

- [ ] **Step 8: Run both test files to verify they pass**

Run: `pytest tests/dq/data/test_gloomberb_models.py tests/dq/data/test_gloomberb_normalizers.py -m unit -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add digiquant/src/digiquant/data/gloomberb/models.py digiquant/src/digiquant/data/gloomberb/normalizers.py digiquant/src/digiquant/data/gloomberb/__init__.py tests/dq/data/test_gloomberb_models.py tests/dq/data/test_gloomberb_normalizers.py
git commit -m "feat(digiquant): saved-searches models and normalizer (#4110)"
```

---

### Task 5: `digifetch_saved_searches` client + all registration surfaces

**Files:**
- Modify: `digiquant/src/digiquant/data/gloomberb/client.py` (imports from `.models` `:99-133`; `ENDPOINTS` `:231-232`; new method after `venues` `~:1573`)
- Modify: `digiquant/src/digiquant/data/gloomberb/entitlements.py:82-96` (add `"digifetch_saved_searches": "session"` under the session block, or `pro` if Task 1 found a Pro gate)
- Modify: `digiquant/src/digiquant/mcp_server.py:489-535` (`READ_SCOPE_TOOLS`) and add a wrapper after `digifetch_venues` (`~:1331`)
- Modify: `digiquant/src/digiquant/orchestrator_tools.py` (builder after `build_digifetch_venues_tool` `:783-796`; manifest list `:1515-1577`)
- Modify: `digiquant/src/digiquant/data/gloomberb/agent_tools.py` (imports `:74-88`; `DIGIFETCH_DISPATCH` `:342-343`)
- Test: `tests/dq/data/test_gloomberb_client.py`, `tests/dq/test_mcp_gloomberb_tools.py`, `tests/dq/test_mcp_server_scope.py` (existing-count updates — see Step 5)

**Interfaces:**
- Consumes: `SavedSearchesInput`/`SavedSearchesEnvelope`/`normalize_saved_searches` (Task 4); `_request_json`, `_data_or_error`, `_as_mapping`, `_normalize`, `_freshness`, `_cached`.
- Produces: `GloomberbClient.saved_searches(request=None) -> SavedSearchesEnvelope`; MCP tool `digifetch_saved_searches() -> str`; manifest entry; `DIGIFETCH_DISPATCH["digifetch_saved_searches"] = DigifetchDispatch(SavedSearchesInput, "saved_searches")` (no deep link — `symbol_field=None`, attributed default True).

- [ ] **Step 1: Write the failing client tests**

Append to `tests/dq/data/test_gloomberb_client.py`:

```python
def test_saved_searches_is_session_gated_and_maps_rows() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        assert request.url.path == "/cloud/search/saved"
        return httpx.Response(200, json={"searches": [{"id": "s1", "name": "AI capex"}]})

    denied = make_client(handler).saved_searches()
    assert denied.data.code == "auth_required"  # type: ignore[union-attr]
    assert calls == []

    allowed = make_client(handler, session_cookie="token").saved_searches()
    assert allowed.data.searches[0].name == "AI capex"  # type: ignore[union-attr]
    assert calls == [1]


def test_saved_searches_401_maps_to_auth_required() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    result = make_client(handler, session_cookie="token").saved_searches()
    assert result.data.code == "auth_required"  # type: ignore[union-attr]
    assert result.data.retryable is False  # type: ignore[union-attr]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/dq/data/test_gloomberb_client.py -m unit -q -k "saved_searches"`
Expected: FAIL — `AttributeError: 'GloomberbClient' object has no attribute 'saved_searches'`.

- [ ] **Step 3: Write the minimal implementation**

In `client.py`, add `"saved_searches": "/cloud/search/saved"` to `ENDPOINTS` (after the phase-1 block, with a `# coverage expansion (#4110 phase 4a)` comment), add `SavedSearchesEnvelope`, `SavedSearchesInput`, `SavedSearchesResult` to the `.models` import, and add after `venues`:

```python
    # -- coverage expansion (#4110 phase 4a) --------------------------------

    def saved_searches(
        self, request: SavedSearchesInput | Mapping[str, Any] | None = None
    ) -> SavedSearchesEnvelope:
        """The signed-in session's saved searches (session-gated).

        Without ``GLOOMBERB_SESSION_COOKIE`` this returns a typed
        ``auth_required`` and makes no request (zero-HTTP gate).
        """
        parsed = self._validate_input(SavedSearchesInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(SavedSearchesEnvelope, parsed)
        if not self._enabled:
            return self._disabled(SavedSearchesEnvelope)

        def produce() -> SavedSearchesEnvelope:
            raw = self._request_json("GET", ENDPOINTS["saved_searches"], gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(SavedSearchesEnvelope, raw)
            result = self._data_or_error(raw, "Cloud saved searches are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(SavedSearchesEnvelope, result)
            data, warnings = result
            normalized = self._normalize(nz.normalize_saved_searches, data)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(SavedSearchesEnvelope, normalized)
            fresh = self._freshness(raw, data)
            return SavedSearchesEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("saved_searches", parsed, produce)
```

- [ ] **Step 4: Run the client tests to verify they pass**

Run: `pytest tests/dq/data/test_gloomberb_client.py -m unit -q -k "saved_searches"`
Expected: PASS.

- [ ] **Step 5: Write the failing MCP + wiring test**

In `tests/dq/test_mcp_gloomberb_tools.py`, add `"digifetch_saved_searches"` to the module-level `DIGIFETCH_TOOLS` set (after `"digifetch_equity_diagnostic"`); do **not** add it to `LINKED_TOOLS` (no deep link).

Adding the name also invalidates three existing assertions — update them in this same step:

- `tests/dq/test_mcp_gloomberb_tools.py:452-454` (`test_all_33_tools_registered_in_full_and_read_scope`): rename to `test_all_34_tools_registered_in_full_and_read_scope` and change `len(DIGIFETCH_TOOLS) == 33` to `== 34`.
- `tests/dq/test_mcp_gloomberb_tools.py:1393-1413` (`test_declared_entitlements_match_the_gate_behavior`): add `"digifetch_saved_searches"` to the hard-coded `"session"` set — or to the `"pro"` set if Task 1's probe moved the entitlement.
- `tests/dq/test_mcp_server_scope.py:163-166` (`test_tool_counts_pin_post_3855_surface`): `len(READ_SCOPE_TOOLS) == 43` → `44` and `len(_tool_names(create_mcp_server())) == 57` → `58` (`COMPUTE_TOOLS` stays 14).

Append:

```python
def test_saved_searches_without_cookie_is_auth_required_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _envelope({"searches": []})

    _patch_client(monkeypatch, handler)
    payload = json.loads(_mcp("digifetch_saved_searches")())
    assert payload["data"]["code"] == "auth_required"
    assert calls == []
    assert payload["attribution"] == GLOOMBERB_ATTRIBUTION
    assert payload["delay_notice"] == GLOOMBERB_DELAY_NOTICE
    assert "source_url" not in payload


def test_saved_searches_maps_rows_with_a_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"searches": [{"id": "s1", "name": "AI capex"}]})

    _patch_client(monkeypatch, handler, session_cookie="gloomberb.session_token=test")
    payload = json.loads(_mcp("digifetch_saved_searches")())
    assert payload["data"]["searches"][0]["name"] == "AI capex"
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/dq/test_mcp_gloomberb_tools.py -m unit -q -k "saved_searches"`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'fn'` (`_tool_manager.get_tool("digifetch_saved_searches")` returns None until the wrapper exists).

- [ ] **Step 7: Write the minimal implementation (all registration points)**

1. `entitlements.py` — add under the `session` block:
```python
    "digifetch_saved_searches": "session",
```
(or `"pro"` if the Task 1 probe found a Pro gate; the MCP test then expects `pro_required` instead of `auth_required`).

2. `mcp_server.py` — add `"digifetch_saved_searches",` to `READ_SCOPE_TOOLS` (after `"digifetch_equity_diagnostic"`) and add after the `digifetch_venues` wrapper:
```python
    @_maybe_tool("digifetch_saved_searches")
    def digifetch_saved_searches() -> str:
        """The signed-in session's saved searches (Gloomberb Cloud; session-gated).

        Requires GLOOMBERB_SESSION_COOKIE; without it the envelope is a typed
        `auth_required` and no request is made. No parameters; rows carry the
        saved-search id/name/query and unknown fields are preserved. Enrichment
        only: the platform's data is delayed - pair with a live web search when
        recency matters.
        """
        try:
            envelope = _build_gloomberb_client().saved_searches()
        except Exception as exc:  # surface as JSON to the caller, never crash
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return _gloomberb_envelope_json(envelope)
```

3. `orchestrator_tools.py` — add the builder after `build_digifetch_venues_tool` and add it to `build_orchestrator_tool_manifest()`'s list (after `build_digifetch_equity_diagnostic_tool()`):
```python
def build_digifetch_saved_searches_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_saved_searches",
            "description": (
                "The signed-in session's saved searches (Gloomberb Cloud; "
                "session-gated). Requires GLOOMBERB_SESSION_COOKIE - without it "
                "the call is a typed auth_required with no request. No "
                "parameters; rows carry the saved-search id/name/query and "
                "unknown fields are preserved. Enrichment only: the platform's "
                "data is delayed."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    }
```

4. `agent_tools.py` — add `SavedSearchesInput` to the `.models` import and the row to `DIGIFETCH_DISPATCH` (after `"digifetch_venues"`):
```python
    "digifetch_saved_searches": DigifetchDispatch(SavedSearchesInput, "saved_searches"),
```

- [ ] **Step 8: Run the full wiring sweep to verify it passes**

Run:
```bash
pytest tests/dq/test_mcp_gloomberb_tools.py -m unit -q
pytest tests/dq/data/test_gloomberb_agent_tools.py -m unit -q
pytest tests/dq/test_mcp_server_scope.py -m unit -q
```
Expected: PASS **only after Step 5's existing-test updates** (the 33→34 set assertion, the session-entitlement set, and the 43/57 scope counts). The parity tests require the name in `TOOL_ENTITLEMENTS`, the manifest, `DIGIFETCH_DISPATCH`, and the MCP wrapper with matching symbol/attribution choices; the scope test pins `READ_SCOPE_TOOLS`. If any parity test fails, one of the four surfaces is missing.

- [ ] **Step 9: Commit**

```bash
git add digiquant/src/digiquant/data/gloomberb/client.py digiquant/src/digiquant/data/gloomberb/entitlements.py digiquant/src/digiquant/mcp_server.py digiquant/src/digiquant/orchestrator_tools.py digiquant/src/digiquant/data/gloomberb/agent_tools.py tests/dq/data/test_gloomberb_client.py tests/dq/test_mcp_gloomberb_tools.py
git commit -m "feat(digiquant): register digifetch_saved_searches on all surfaces (#4110)"
```

---

### Task 6: Docs, verification sweep, PR

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (§5 digifetch table rows and/or the phase-3 paragraph; §11 Gloomberb bullet; the tool-count sentence `:276-282`; the "Deliberately out of scope" paragraph `:1334-1347`)
- Modify: `digiquant/AGENTS.md:474+` (family size, saved-searches mention, remove the "per-transcript detail route remains a candidate extension" sentence `:617-618`)
- Modify: `digiquant/src/digiquant/mcp_server.py:485` (the `"33 digifetch x"` comment)
- Test: the full offline sweep (no new test file)

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: docs that match the shipped 34-tool family and a PR.

- [ ] **Step 1: Update the docs**

- `digiquant/ARCHITECTURE.md:276-282`: `all 57 tools` → `all 58`; `only the 43 dashboard-chat reads` → `44`; `the 33 digifetch_*` → `the 34 digifetch_*`.
- `digiquant/ARCHITECTURE.md` §5 table: extend the `digifetch_transcripts` row with the `transcript_id` detail mode; add a `digifetch_saved_searches` row (`/cloud/search/saved`, session-gated, parameterless).
- `digiquant/ARCHITECTURE.md:1345-1347`: the sentence "The per-transcript detail route (`/cloud/transcripts/{id}`) exists and remains a candidate extension" → "The per-transcript detail route (`/cloud/transcripts/{id}`) shipped as `digifetch_transcripts`' `transcript_id` mode (#4110 phase 4a); `digifetch_saved_searches` covers `/cloud/search/saved`."
- `digiquant/ARCHITECTURE.md` §11 Gloomberb bullet: `The family is 33 read tools total` → `34`; add the phase-4a sentence (`transcripts` detail mode + `saved_searches`) and note the remaining scope (plugin panes per the paragraph, surface integration #4098).
- `digiquant/AGENTS.md` Gloomberb section: `**33 tools**` → `**34 tools**`; add `digifetch_saved_searches` to the phase-3 cohort list (or a new phase-4a clause); replace the sentence at `:617-618` ("the per-transcript detail route (`/cloud/transcripts/{id}`) remains a candidate extension") with "the per-transcript detail route (`/cloud/transcripts/{id}`) is `digifetch_transcripts`' `transcript_id` mode."
- `mcp_server.py:485` comment: `the 33 digifetch x` → `the 34 digifetch x`.

- [ ] **Step 2: Run the full verification sweep**

Run:
```bash
pytest tests/dq/test_mcp_gloomberb_tools.py tests/dq/test_mcp_server_scope.py \
       tests/dq/data/test_gloomberb_agent_tools.py tests/dq/data/test_gloomberb_client.py \
       tests/dq/data/test_gloomberb_models.py tests/dq/data/test_gloomberb_normalizers.py \
       -m unit -q
ruff check digiquant/ && ruff format --check digiquant/
python - <<'PY'
from digiquant.data.gloomberb import TOOL_ENTITLEMENTS
print(len(TOOL_ENTITLEMENTS), "digifetch tools")
PY
make doc-check
```
Expected: all green **only after Task 5's existing-test updates** (33→34 set, session-entitlement set, 43/57 scope counts); `34 digifetch tools`; `make doc-check` passes (updated internal links).

- [ ] **Step 3: Commit the docs**

```bash
git add digiquant/ARCHITECTURE.md digiquant/AGENTS.md digiquant/src/digiquant/mcp_server.py
git commit -m "docs(digiquant): record phase-4a digifetch coverage (#4110)"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin "$(git branch --show-current)"
gh pr create --base module/digiquant \
  --title "feat(digiquant): digifetch phase 4a — transcripts detail + saved searches (#4110)" \
  --body "$(cat <<'EOF'
Advances #4110 (phase 4a): the two residual endpoints of the coverage matrix.

- `digifetch_transcripts` gains a `transcript_id` detail mode (`GET /cloud/transcripts/{id}`); exactly one of `ticker`/`transcript_id`; Pro/session semantics unchanged (typed `pro_required`).
- New `digifetch_saved_searches` (`GET /cloud/search/saved`), session-gated, parameterless.
- Registered on all surfaces: `TOOL_ENTITLEMENTS`, `READ_SCOPE_TOOLS`, MCP wrapper, orchestrator manifest, `DIGIFETCH_DISPATCH`; parity tests pin them.

Spec: docs/superpowers/specs/2026-09-16-digifetch-coverage-expansion-design.md
Plan: docs/superpowers/plans/2026-09-16-digifetch-coverage-expansion.md

Phases 4b (plugin panes) and 4c (surface integration, #4098) remain open in #4110 — this PR does not close the issue.
EOF
)"
```

- [ ] **Step 5: Merge when ready (per AGENTS.md)**

Run `/review <PR>` (fresh-context), post the findings as a `<!-- in-session-review -->` comment, apply `reviewed:agent`, wait for required CI, then `gh pr merge <PR>` into `module/digiquant`. No human gate applies (no new external dependency).

---

## Self-Review

**1. Spec coverage.** Spec §4 tool contracts → Tasks 2-5 (transcripts input/normalizer, client/MCP, saved-searches models/normalizer, client/registration). Spec §5 NFRs → inherited, not re-implemented; Global Constraints repeat the numbers. Spec §6 coverage matrix residual rows → Tasks 2-5. Spec §7 phase 4a plan split → this plan's header + Task 6. Spec §8 verification → Task 6 Step 2 (grep counts are covered by the parity/scope tests asserting the same surfaces). Spec §7 decisions D3/D4 → Task 2/3 (fold) and Task 4/5 (new tool). D7 human gate → Global Constraints + Task 6 Step 5. Probe-first (D8, §11) → Task 1. The deferred classes (4b/4c) are deliberately not tasked.

**2. Placeholder scan.** No "TBD"/"add error handling"/"similar to Task N": every code step carries full code; every run step has a command and expected result; the only conditional is the Task 1 go/no-go, which has explicit criteria and an explicit fallback.

**3. Type consistency.** `TranscriptId` (Task 2) → `TranscriptsInput.transcript_id` (Tasks 2, 3, 5); `normalize_transcript_detail(raw, fallback_id)` (Task 2) is called with exactly those parameters in Task 3's client code; `SavedSearchesInput` has no fields and the dispatcher row/Task 5 wrapper call it with `{}`/no args; `SavedSearchesResult.searches` matches the normalizer and the client return; the dispatcher row name `digifetch_saved_searches` matches every registration point and the test set. Method names `transcripts` / `saved_searches` match the dispatcher `client_method` strings. `SavedSearchesEnvelope` is added to `__init__.py` before tests import it from the package.
