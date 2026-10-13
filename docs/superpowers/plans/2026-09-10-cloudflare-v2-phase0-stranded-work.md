# Phase 0 — cloudflare v2 refactor: rebase stranded MCP scope work

Plan header:
- Goal: rebase the uncommitted task/3780 MCP scope + boot-fix work onto current
  `origin/develop` (which now carries PR #3855), add the new
  `digiquant_list_coinmetrics_catalog` tool to the read scope, fix the same
  `FastMCP.run(host, port)` boot crash in digigraph + digillm, and resolve the
  `:8766` MCP default-port collision between digivault and digigraph.
- Architecture: four FastMCP `streamable-http` servers (digigraph, digiquant,
  digisearch, digivault) plus the digillm completion server; digiquant gains a
  `scope="read" | "full"` registration gate. No new services, no new ports
  except the digivault move. Cloudflare worker mapping itself is Phase 1+.
- Tech Stack: Python 3.12, FastMCP from pinned `mcp==1.29.0` (`uv.lock`:
  `name = "mcp" / version = "1.29.0"`), pytest `-m unit`, ruff (line-length
  100, `ruff.toml`).
- Spec: this file —
  `docs/superpowers/plans/2026-09-10-cloudflare-v2-phase0-stranded-work.md`.

## Global Constraints

- TDD RED-first: write/update the failing test before touching `src/`
  (repo `AGENTS.md` quality bar; digiquant/digigraph `AGENTS.md` pre-flight:
  `pytest tests/ -m unit -k "<component>"` passes before AND after).
- digi names always lowercase in prose/docs/commit messages (`AGENTS.md` § Naming).
- Update `digiquant/ARCHITECTURE.md` (§ MCP server, currently lines 212, 265–273)
  and `digigraph/ARCHITECTURE.md` / `digillm/ARCHITECTURE.md` on any interface
  change (root `AGENTS.md` § Before modifying a component).
- Gates: `pytest -m unit -k digigraph`; `pytest -m unit` on
  `tests/dq/test_mcp_server_scope.py tests/ds/test_mcp_server_bind.py
  tests/dv/test_mcp_server_bind.py tests/dg/test_mcp_server.py
  digillm/tests/test_mcp_server.py`; `ruff check <component>/` +
  `ruff format --check <component>/` (line-length 100).
- Never touch `sleepAfter`/scaling (`digiquant/ARCHITECTURE.md:299`) — #3851
  lives in another session.
- Never touch repos outside digithings (no zeus/apollo); stay on a
  `task/<N>-slug` branch cut from current `origin/develop` (`BRANCHING.md`;
  tracking issue: #3854, already cited in the stranded test docstrings).
- Secrets never in files (`.env` / env vars only; gitleaks gate stays green).
- Spec only — this plan makes zero `src/` edits itself.

## Verified starting state (read 2026-09-10, do not re-derive — verify with `git status`)

- Branch `task/3780-r2-market-data-cache-cutover` carries uncommitted scope work:
  `M digiquant/ARCHITECTURE.md`, `M digiquant/src/digiquant/mcp_server.py`,
  `M digisearch/src/digisearch/mcp_server.py`, `M digivault/src/digivault/mcp_server.py`,
  plus untracked `tests/dq/test_mcp_server_scope.py`,
  `tests/ds/test_mcp_server_bind.py`, `tests/dv/test_mcp_server_bind.py`.
- Local `develop` is STALE (tip `a89f76cfe`); PR #3855 (merge `8bc88663f`) is
  only on `origin/develop`. Always diff against `origin/develop`, never local.
- `origin/develop` `digiquant/src/digiquant/mcp_server.py` = 23 tools
  (21 × `@mcp.tool()` + 2 × `@mcp.tool(name=...)` for price/macro), NO scope
  consts, and the crash bug intact:
  `mcp.run(transport=transport, host=host, port=port)`.
- Installed `mcp` 1.29.0 signature (verified in `.venv`):
  `FastMCP.run(self, transport='stdio', mount_path=None)` — `host`/`port` live
  on `FastMCP(...)` constructor / `.settings`. Any `run(..., host=, port=)`
  call raises `TypeError` on boot.
- Port defaults today: digisearch `:8765`, digigraph `:8766`
  (`digigraph/src/digigraph/mcp_server.py:267`), digivault `:8766`
  (`digivault/src/digivault/mcp_server.py:39`), digiquant `:8767`,
  digillm `:8768` (`digillm/src/digillm/mcp_server.py:132`). No in-repo client
  hardcodes `:8766` (grepped `digi*/src`, `scripts/`, `config/`) — the
  collision bites only when both servers boot with defaults.
- This checkout has NO `digiquant/data/onchain/{coinmetrics,bgeometrics}.py`
  and NO `run_fetch_coinmetrics_series` in `sdca_mcp.py` — rebase brings them.

---

## Task 0 — sync base + inventory stranded work (no src edits)

Files: none (git operations only).

Interfaces: consumes `origin/develop` + `git diff`; produces a clean task
branch and a tool inventory both implementers trust.

- [ ] `git fetch origin && git status --short` — confirm the 4 modified +
      3 untracked paths above, nothing else.
- [ ] Cut a fresh branch from current remote:
      `git checkout -b task/3854-cloudflare-v2-phase0 origin/develop`
      (per `BRANCHING.md`; `make task ISSUE=3854` is equivalent).
- [ ] Port the stranded hunks as a reference diff (do NOT apply blindly):
      `git diff task/3780-r2-market-data-cache-cutover -- digiquant/src/digiquant/mcp_server.py > /tmp/scope-wip.diff`
      and confirm it contains `READ_SCOPE_TOOLS`, `_MCP_SCOPES`,
      `create_mcp_server(scope`, `_maybe_tool`, `--scope`,
      `DIGIQUANT_MCP_SCOPE`, `FastMCP("digiquant", host=host, port=port)`.
- [ ] Confirm the conflict zone on `origin/develop`:
      `digiquant_fetch_bgeometrics_series` (`mcp_server.py:851`),
      `digiquant_fetch_coinmetrics_series` (`:892`),
      `digiquant_list_coinmetrics_catalog` (`:931`, plain `@mcp.tool()`),
      `run_list_coinmetrics_catalog` (`sdca_mcp.py:148`).

```bash
git fetch origin
git checkout -b task/3854-cloudflare-v2-phase0 origin/develop
git diff task/3780-r2-market-data-cache-cutover --stat -- digiquant digisearch digivault tests
```

## Task 1 — RED: extend the scope test to the 23-tool post-#3855 surface

Files: `tests/dq/test_mcp_server_scope.py` (exists in stranded work, lines
1–81: `_tool_names` helper via `list_tools_sync`/`_tool_manager`, `COMPUTE_TOOLS`
set of 12, 5 tests).

Interfaces: consumes `digiquant.mcp_server.create_mcp_server`,
`READ_SCOPE_TOOLS`; produces the failing spec for Task 2.

- [ ] Add the two network-fetch tools to `COMPUTE_TOOLS`
      (same rule as `digiquant_fetch_bitview_series`: network fetch + cache
      write ⇒ full-only):
      `"digiquant_fetch_bgeometrics_series"`,
      `"digiquant_fetch_coinmetrics_series"`.
- [ ] Assert the read set is exactly the old 8 + catalog (read-natured
      discovery GET, fail-soft — no fetch, no cache write, no mutate):
      `"digiquant_list_coinmetrics_catalog" in set(READ_SCOPE_TOOLS)`.
- [ ] Keep the exact-equality pins — they are the rebase tripwire:
      `names == READ_SCOPE_TOOLS | COMPUTE_TOOLS` (full) and
      `names == set(READ_SCOPE_TOOLS)` (read). Full must be 23, read must be 9.
- [ ] Run RED and record the failure (unknown names on `origin/develop`
      without scope code — `ImportError`/`AssertionError`, never green):
      `pytest tests/dq/test_mcp_server_scope.py -m unit -v`.

Actual test code (append/replace in `tests/dq/test_mcp_server_scope.py`):

```python
READ_TOOLS_EXTRA = {"digiquant_list_coinmetrics_catalog"}

COMPUTE_TOOLS = {
    "digiquant_run_backtest",
    "digiquant_run_optimize",
    "digiquant_export",
    "digiquant_run_pipeline",
    "digiquant_fetch_coinbase_ohlcv",
    "digiquant_fit_btc_power_law",
    "digiquant_build_sdca_risk_index",
    "digiquant_fetch_bitview_series",
    "digiquant_fetch_bgeometrics_series",
    "digiquant_fetch_coinmetrics_series",
    "digiquant_fit_sdca_weights",
    "digiquant_generate_slapper_tearsheet",
    "digiquant_validate_slapper_vs_tradingview",
    "dashboard_run_policy_replay",
}


@pytest.mark.unit
def test_read_scope_includes_coinmetrics_catalog():
    assert READ_TOOLS_EXTRA <= set(READ_SCOPE_TOOLS)


@pytest.mark.unit
def test_tool_counts_pin_post_3855_surface():
    assert len(READ_SCOPE_TOOLS) == 9
    assert len(COMPUTE_TOOLS) == 14
    assert len(_tool_names(create_mcp_server())) == 23
```

## Task 2 — GREEN: re-apply scope gating on `origin/develop` digiquant server

Files:
- `digiquant/src/digiquant/mcp_server.py` — rebase target: `create_mcp_server()
  -> Any` (`origin/develop:418`), module-level plain functions
  `digiquant_get_price_technicals` (`:300`) / `digiquant_get_macro_series`
  (`:353`), named tools `:542`/`543` + `:555`/`556`, new tools `:851/:892/:931`,
  `run_mcp` (`:1163`, still `mcp.run(transport=transport, host=host, port=port)`
  — the crash), argparse (`:1173–1183`, no `--scope` yet).
- `digiquant/ARCHITECTURE.md:212` (`:8767` bind) and `:265–273`
  ("registers all 20 tools" — stale after #3855 even before scope).

Interfaces: consumes `run_list_coinmetrics_catalog` (`sdca_mcp.py:148`),
`COINMETRICS_BASE_URL`; produces `READ_SCOPE_TOOLS` (9),
`_MCP_SCOPES = ("full", "read")`,
`create_mcp_server(scope="full", host="127.0.0.1", port=8767)`.

- [ ] Add `READ_SCOPE_TOOLS` = the 8 stranded names +
      `"digiquant_list_coinmetrics_catalog"`; add `_MCP_SCOPES`; add
      `scope/host/port` params to `create_mcp_server`; construct
      `FastMCP("digiquant", host=host, port=port)` (constructor, never `run()`).
- [ ] Wrap ALL 23 registrations with the stranded `_maybe_tool(name)` decorator
      (fetch_bgeometrics + fetch_coinmetrics_series ⇒ full-only;
      list_coinmetrics_catalog ⇒ read). Keep the two `name=` registrations for
      price/macro (their registered names, not the `*_tool` function names, go
      in the read set).
- [ ] Thread scope through `run_mcp(..., scope="full")` + argparse `--scope`
      (default `os.environ.get("DIGIQUANT_MCP_SCOPE", "full")`); `run_mcp` calls
      `create_mcp_server(scope=scope, host=host, port=port)` then
      `mcp.run(transport=transport)` only.
- [ ] Update `digiquant/ARCHITECTURE.md:268–273`: "all 23 tools" / read = 9
      (strategy list, price/macro reads, `query_data`, policy replay/comparison
      reads, gate reads + evaluations, coinmetrics catalog).
- [ ] GREEN: `pytest tests/dq/test_mcp_server_scope.py -m unit -v` (23/9 pins
      pass); `pytest tests/ -m unit -k "digiquant" -v`;
      `ruff check digiquant/ && ruff format --check digiquant/`.

## Task 3 — digigraph `run_mcp(host, port)` boot crash (settings pattern)

Files:
- `digigraph/src/digigraph/mcp_server.py:90` (`create_mcp_server()`, no
  bind params), `:105` (`FastMCP("digigraph")`), `:264–273` (`run_mcp` calls
  `mcp.run(transport=transport, host=bind, port=port)` — the crash),
  `:283` (`--port` default `8766` — unchanged).
- `tests/dg/test_mcp_server.py:11–22` (`test_mcp_default_bind_is_loopback`
  fakes `get_mcp_server` and asserts `run()` RECEIVED `host=` — this test
  pins the buggy call shape and MUST change).

Interfaces: consumes `get_mcp_server()` singleton; produces settings-bound
bind + transport-only `run()`.

- [ ] RED: extend `tests/dg/test_mcp_server.py` with a transport-only pin
      (mirrors stranded `tests/ds/test_mcp_server_bind.py:18–30`):

```python
@pytest.mark.unit
def test_run_mcp_applies_bind_to_settings_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph import mcp_server

    calls: dict[str, object] = {}

    class _FakeSettings:
        host = "127.0.0.1"
        port = 8766

    class _FakeMcp:
        settings = _FakeSettings()

        def run(self, **kwargs: object) -> None:
            calls.update(kwargs)

    monkeypatch.setattr(mcp_server, "get_mcp_server", lambda: _FakeMcp())
    mcp_server.run_mcp(host="0.0.0.0", port=8123)
    assert calls == {"transport": "streamable-http"}
    assert (_FakeMcp.settings.host, _FakeMcp.settings.port) == ("0.0.0.0", 8123)
```

- [ ] Rewrite `test_mcp_default_bind_is_loopback` (lines 11–22): it asserts the
      old `run(host=...)` shape — change the fake to capture `settings` +
      `run kwargs`, call `run_mcp(host=None)`, assert settings host stayed
      `127.0.0.1` and `run kwargs == {"transport": "streamable-http"}`.
- [ ] GREEN: `run_mcp` sets `mcp.settings.host = bind` /
      `mcp.settings.port = port` (bind = `host or
      os.environ.get("DIGIGRAPH_MCP_HOST", "127.0.0.1")`, same as today) then
      `mcp.run(transport=transport)`. Keep `create_mcp_server()` signature
      (singleton callers untouched) and port default `8766`.
- [ ] `pytest tests/ -m unit -k "digigraph" -v`;
      `ruff check digigraph/ && ruff format --check digigraph/`;
      update `digigraph/ARCHITECTURE.md` § MCP only if the bind contract text
      changes (keep `:8766` everywhere: lines 4, 102, 706, 1046–1053).

## Task 4 — digillm `run_mcp(host, port)` boot crash (same pattern)

Files:
- `digillm/src/digillm/mcp_server.py:129–138` (`run_mcp` calls
  `mcp.run(transport=transport, host=bind, port=port)` — the crash),
  `:48` (module-level `mcp` singleton), `:141–151` (`main()` CLI, port default
  from `DIGILLM_MCP_PORT` else `8768` — unchanged).
- `digillm/tests/test_mcp_server.py` (5 tests, no bind test; `pytest.ini`
  `testpaths` already includes `digillm/tests`).

Interfaces: consumes module-level `mcp.settings`; produces transport-only run.

- [ ] RED: add `test_run_mcp_applies_bind_to_settings_not_run` to
      `digillm/tests/test_mcp_server.py` (same shape as the stranded
      `tests/ds/test_mcp_server_bind.py`, save/restore settings):

```python
@pytest.mark.unit
def test_run_mcp_applies_bind_to_settings_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digillm import mcp_server

    calls: dict = {}
    monkeypatch.setattr(type(mcp_server.mcp), "run", lambda self, **kw: calls.update(kw))
    old_host, old_port = mcp_server.mcp.settings.host, mcp_server.mcp.settings.port
    try:
        mcp_server.run_mcp(host="0.0.0.0", port=8128)
        new_host, new_port = mcp_server.mcp.settings.host, mcp_server.mcp.settings.port
    finally:
        mcp_server.mcp.settings.host = old_host
        mcp_server.mcp.settings.port = old_port
    assert calls == {"transport": "streamable-http"}
    assert (new_host, new_port) == ("0.0.0.0", 8128)
```

- [ ] GREEN: `run_mcp` sets `mcp.settings.host`/`mcp.settings.port`, calls
      `mcp.run(transport=transport)`.
- [ ] `pytest digillm/tests/test_mcp_server.py -m unit -v`;
      `ruff check digillm/ && ruff format --check digillm/`.

## Task 5 — resolve `:8766` collision: digivault moves to `:8769`

Decision: digigraph keeps `8766` (documented in `digigraph/ARCHITECTURE.md`
lines 4, 102, 706, 1046–1053 + historical audit docs `docs/adr/0028…:71`,
`docs/reviews/2026-06-full-audit.md:12,58,200` — all digigraph-scoped, stay
valid). digivault moves to the next free port `8769` (8765 digisearch, 8766
digigraph, 8767 digiquant, 8768 digillm — verified no other claimant).

Files:
- `digivault/src/digivault/mcp_server.py:3` (docstring default), `:39`
  (`port: int = 8766`), `:41` (run_mcp docstring).
- `digivault/ARCHITECTURE.md:45` (default `127.0.0.1:8766`).
- `tests/dv/test_mcp_server_bind.py` (stranded; uses explicit port 8126 —
  unaffected, keep).

Interfaces: consumes nothing new; produces default `127.0.0.1:8769` for
digivault MCP. No `DIGIVAULT_MCP_PORT` env exists today (grepped
`digivault/`, `scripts/`, `config/`, `docs/` — zero hits); do NOT mint one
in Phase 0 (open question below).

- [ ] RED: add a default-port pin to `tests/dv/test_mcp_server_bind.py`:

```python
@pytest.mark.unit
def test_default_port_does_not_collide_with_digigraph():
    import inspect

    from digivault import mcp_server

    default_port = inspect.signature(mcp_server.run_mcp).parameters["port"].default
    assert default_port == 8769
    assert default_port != 8766  # digigraph keeps 8766
```

      (Signature introspection — no server boot, no digigraph import.)
- [ ] Optionally mirror in `tests/dg/test_mcp_server.py`: digigraph default
      stays `8766` via the same `inspect.signature` pattern.
- [ ] GREEN: change the three digivault lines to `8769`; update
      `digivault/ARCHITECTURE.md:45` to `127.0.0.1:8769`.
- [ ] Grep for strays: `grep -rn "8766" digivault/ docs/ --include="*.py"
      --include="*.md"` must show no digivault-scoped `:8766` outside
      `build/` artifacts, `__pycache__`, and `.claude/worktrees/` mirrors
      (never touch worktree mirrors or `build/` output).
- [ ] `pytest tests/dv -m unit -v`; `ruff check digivault/src tests/dv &&
      ruff format --check digivault/src tests/dv`.

## Task 6 — full gates + doc-check (no src edits)

- [ ] `pytest -m unit -k digigraph -v --tb=short` (required gate per brief).
- [ ] `pytest tests/dq/test_mcp_server_scope.py tests/ds/test_mcp_server_bind.py
      tests/dv/test_mcp_server_bind.py tests/dg/test_mcp_server.py
      digillm/tests/test_mcp_server.py -m unit -v`.
- [ ] `ruff check digiquant digigraph digisearch digivault digillm tests/dq/test_mcp_server_scope.py tests/ds/test_mcp_server_bind.py tests/dv/test_mcp_server_bind.py tests/dg/test_mcp_server.py digillm/tests/test_mcp_server.py && ruff format --check` on the same set.
- [ ] `make doc-check` (ARCHITECTURE.md edits must not break internal links).
- [ ] Boot-smoke each fixed server (proves the `TypeError` is gone; kill after
      bind line appears — do NOT leave servers running):
      `timeout 8 python -m digiquant.mcp_server --help` (shows `--scope`),
      plus one transport boot each for digigraph/digillm/digivault/digisearch
      and `curl -s 127.0.0.1:<port>/mcp` expecting a non-`TypeError` response.

## Acceptance criteria

- `create_mcp_server(scope="read")` exposes exactly 9 tools including
  `digiquant_list_coinmetrics_catalog`; `scope="full"` (default) exposes
  exactly 23; `scope="everything"` raises `ValueError`; `--scope` /
  `DIGIQUANT_MCP_SCOPE` plumb through; no `run(host=, port=)` call remains in
  any of the five `run_mcp` entrypoints (`grep -rn "run(transport" */src/*/mcp_server.py`).
- digigraph default `:8766`, digivault default `:8769`; both pinned by tests.
- All gates in Task 6 green; `digiquant/ARCHITECTURE.md` tool counts read
  23/9; `make doc-check` green.

## Rollback

- Each task is its own commit on `task/3854-cloudflare-v2-phase0`; revert per
  commit. Scope work is purely additive gating (default `full` preserves the
  23-tool surface), so reverting Task 2 restores today's behavior minus #3855
  tools (which ship from `origin/develop` regardless).
- Port move revert: single constant back to `8766` in
  `digivault/src/digivault/mcp_server.py:39` + ARCHITECTURE line 45; no data
  migration, no client config in-repo to unwind.

## Risks

- Rebase drift: `origin/develop` moved since the 3780 checkout's last merge
  (`753a0de59`) — the `_maybe_tool` wrap must cover all 23 current tools; the
  exact-count pins in Task 1 fail loud if a tool is added/removed meanwhile.
- `FastMCP` constructor `host`/`port` kwargs are version-pinned behavior
  (`mcp==1.29.0`, `>=1.2,<2` bound per `AGENTS.md` context policy) — if a
  deliberate `mcp` upgrade lands mid-Phase 0, re-verify
  `FastMCP.run`/`__init__` signatures in `.venv` before merging.
- `tests/dg/test_mcp_server.py::test_mcp_default_bind_is_loopback` currently
  pins the BUGGY shape — Task 3 rewrites it; do not "fix" the implementation
  to satisfy the old assertion.
- Port `8769` is free in-repo but unverified against operator-local usage
  (`.env`, Claude Desktop configs outside the repo) — announce the move in
  the PR body.
