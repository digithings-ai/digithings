# Review — PR #4945 (commit e05ebabfd)

- Reviewer: OpenCode review subagent
- Subject: PR #4945, commit e05ebabfd (`feat(zammad): expose full customer names/emails and internal articles for OCC demo`, Fixes #4944)
- Verdict: **approve-with-nits**
- Severity counts: high 0 / medium 0 / low 2 / info 1

Scope: 5 files — `scripts/zammad_mcp/formatting.py`, `scripts/zammad_mcp/server.py`,
`scripts/zammad_mcp/aggregate.py` (comment only), `scripts/zammad_mcp/README.md`,
`tests/scripts/test_zammad_mcp.py`. All findings verified by reading file content, not from the diff alone.

## (1) Remaining masking / omission — clean

- Grep (case-insensitive) for `mask|k***|m***|omit|internal note` over `scripts/zammad_mcp/`:
  no `_mask_customer`, `_EMAIL_RE`, `***`, `hidden`, or `internal note(s) omitted` remains.
- Remaining `omit*` hits are benign and unrelated to PII/internal filtering:
  - `scripts/zammad_mcp/formatting.py:295` — `"... {remaining} more article(s) omitted"`: the
    pre-existing `MAX_ARTICLES_SHOWN = 50` cap (formatting.py:20), still correct; pinned by
    `test_format_ticket_detail_limits_article_count` (tests/scripts/test_zammad_mcp.py:274-277).
  - `scripts/zammad_mcp/server.py:186` — `None (omitted) on failure`: state-category fallback, not articles.
  - `scripts/zammad_mcp/README.md:12` — `line omitted when resolution fails`: Owner/Category line, not articles.
- Grep for `anonymous|conservative|leak|PII|NEVER emit|masked|_mask_customer|_EMAIL_RE|hidden`
  over `scripts/zammad_mcp/`: only intentional new-behavior wording
  (`formatting.py:108` `no masking`, `formatting.py:396` `never masked`,
  `server.py:323` `no masking`). No stale privacy claims.

## (2) `_display_customer` correctness

- `scripts/zammad_mcp/server.py:252-265` — all branches correct:
  empty/None → `(id N)`; `cid is None` → bare text; else `text (id N)`.
  Pinned by `test_display_customer_format_and_fallback`
  (tests/scripts/test_zammad_mcp.py:1303-1314), including non-email passthrough
  (`Ada Lovelace (id 5)`), `?` cid, and `None` cid.
- `scripts/zammad_mcp/formatting.py:107-113` — correct for the string path
  (all current fixtures/tests use strings); `_field` handles `None`/`-`/whitespace.
  See nit-1 below for the dict branch.

## (3) `format_ticket_detail` article rendering

- `scripts/zammad_mcp/formatting.py:248,290-296`: `shown = list(articles)`, count is
  `len(shown)`, loop over `shown[:MAX_ARTICLES_SHOWN]` — all articles shown up to the
  documented 50-cap. No `hidden`/omitted-internal logic remains.
- Internal tagging via `_format_article`, `formatting.py:211-212`
  (`if article.get("internal"): header_bits.append("[internal]")`) — correct.
- Pinned by `test_format_ticket_detail_includes_internal_notes`
  (tests/scripts/test_zammad_mcp.py:238-260): both bodies present, `[internal]` present,
  `Articles (2)`, and `"internal note(s) omitted" not in out`.

## (4) Tests pin the new behavior

- `tests/scripts/test_zammad_mcp.py:210` — search line shows `customer: jane.doe@example.test` in full.
- `tests/scripts/test_zammad_mcp.py:263-265` — ticket line shows full email.
- `tests/scripts/test_zammad_mcp.py:958-963` — aggregate renders full customer, raw `7` passes through.
- `tests/scripts/test_zammad_mcp.py:1317-1349` — aggregate customer branches keep full
  `jane.doe@example.test (id 7)` while dropping automation pre/post-rank.
- `tests/scripts/test_zammad_mcp.py:1352-1360,1389-1403` — enriched full displays
  (`Hans Müller (id 9)`) render; server-level test also bounds user lookups to `7, 9`.
- Old negative assertions (`jane.doe not in …`) correctly removed/replaced with positives.
  See info-1 for optional hardening.

## (5) Docstring / README consistency

- Consistent: `formatting.py:107-111,234-240,393-398`; `server.py:252-259,268-277,322-323`;
  `aggregate.py:165-166`; `README.md:15,42,125-130` (demo-mode wording, `[internal]` tag,
  `name/email (id N)`); `server.py:151` `get_ticket` "with all of its articles" matches
  the unfiltered implementation. `ruff check` passes.

## Verification runs

- `python3 -m pytest tests/scripts/test_zammad_mcp.py -q`: 97 passed, 16 skipped
  (`mcp` not installed in this env), 1 failed —
  `test_allowed_host_patterns_append_port_wildcard` fails with
  `ModuleNotFoundError: No module named 'mcp'` at `server.py:15`, environmental and
  unrelated to this diff (no `server.py` import-path change in this PR).
- `ruff check scripts/zammad_mcp/ tests/scripts/test_zammad_mcp.py`: all checks passed.

## Findings

- nit-1 (low) — `scripts/zammad_mcp/formatting.py:113`: dict branch reads only
  `.get("email")`, so a dict customer carrying only `login`/`name` yields `""` and the
  `Customer:` label is dropped. `scripts/zammad_mcp/server.py:283-284` in contrast falls
  back `email → login → name`. Pre-existing shape (old `_mask_customer` was identical),
  not a regression — but for "full names" completeness, consider
  `_field(value) if _field(email) == ""` or delegating to `_field(value)` for dicts.
- nit-2 (low) — `scripts/zammad_mcp/server.py:263-264` (`if cid is None: return text`):
  unreachable via `_customer_display_names` (`server.py:296` substitutes `"?"` when
  `cid is None`), so it is a direct-call-only fallback. Harmless and tested
  (`test_zammad_mcp.py:1314`); optionally simplify the call site or drop the branch.
- info-1 — No test asserts the *absence* of masking (e.g. `"***" not in out` on a detail/
  aggregate render). Positive full-value assertions plus deleted mask code make this
  redundant, but a one-line negative assertion would harden against a masking relapse.
