# Review — PR #5155 (OCC customer PII mask)

- **Subject:** `d608c5df4` fix(zammad): mask customer PII by default in the OCC help surfaces → branch `task/1063-zammad-mask-customer-pii`, PR #5155
- **Reviewer:** fresh-context `general` subagent (`ses_ef24d7da2ffe95uC8J0f1Yj8N5`), spawned by the Platform agent that authored the branch
- **Date:** 2026-10-05
- **Verdict:** request changes → all findings addressed in `c0d5814f4`
- **Severity counts:** 2 high, 4 medium, 4 low — all 10 addressed; 3 residual limits recorded as documented limitations rather than code changes (see § Accepted limitations)
- **Scope:** `scripts/zammad_mcp/{formatting,server}.py`, `scripts/zammad_mcp/README.md`, `tests/scripts/test_zammad_mcp.py`, `docker-compose.yml`, `apps/digithings-stack-cloudflare/{src/index.ts,wrangler.toml}`, `infra/digichat-release/compose.profile-a-bundle.override.yml`

## Reviewer independence

The reviewer is a separate session with no authorship context. Per
`docs/agents/CODE_REVIEW_POLICY.md` the author session must not review its own
work, so this review is real coverage rather than a self-check.

## Verification run

| Check | Command | Result |
|---|---|---|
| Zammad MCP suite | `pytest tests/scripts/test_zammad_mcp.py tests/scripts/test_zammad_mcp_stack.py -q` | 149 passed |
| Prompt parity gate | `pytest tests/scripts/test_check_tenant_corpus_map.py -q` | 12 passed — all three corpus-map blobs still byte-identical after decoding |
| Lint / format | `ruff check` + `ruff format --check` | clean |
| Line length | `awk 'length>100'` on touched Python | clean |
| Worker env forwarding | `vitest run src/env-vars-pin.test.js` | 7 passed |
| Worker typecheck | `tsc --noEmit` | no error on any changed line; the run reports only missing-package errors from an incomplete `node_modules` (`@cloudflare/workers-types`, `hyparquet`), all pre-existing |
| Worker suite | `vitest run` | 80 passed; 2 files fail to import `hyparquet` — same incomplete install, unrelated |
| **Falsification** | `git checkout origin/develop -- scripts/zammad_mcp/{formatting,server}.py` then re-run | **30 failed, 119 passed.** The suite genuinely pins the change; it is not green by accident. |

## Findings

### 1. HIGH — internal `ticket.note` rendered on the default path

`scripts/zammad_mcp/formatting.py` — `note = _field(ticket.get("note")); if note: lines.append(f"Note: {note}")`

The new omission logic filtered **articles** only. Zammad's `ticket.note` is an
internal-only field on `GET /api/v1/tickets/:id`; Zammad's own documentation
states it "is currently only an internal field and not rendered to the
frontend", and the payload carries it. So an internal staff note still reached
the anonymous OCC embed on every `get_ticket`, bypassing the
`... N internal note(s) omitted` line entirely and contradicting both the
README and DIG-1063 requirement 1.

Fixed: the field is now gated behind `demo_unmasked_pii()` alongside internal
articles, with tests in both directions.

### 2. HIGH — the deployed OCC prompt promised a contract that no longer existed

`apps/digithings-stack-cloudflare/src/index.ts` (`_FALLBACK_RE` literal),
`apps/digithings-stack-cloudflare/wrangler.toml` (`[vars]`),
`infra/digichat-release/compose.profile-a-bundle.override.yml` — all three said:

> "customer names and emails are **shown in full (demo mode)**; internal ticket
> notes are **included** and tagged [internal]."

Left alone, the assistant would have told anonymous OCC visitors their data is
shown in full when it no longer is. `tests/scripts/test_check_tenant_corpus_map.py::test_real_blobs_occ_prompt_parity`
pins the three copies byte-identical after decoding, so they had to move
together. `json.dumps` round-tripping is not stable for any of the three, so
the patch was applied as targeted raw-fragment replacement.

Fixed: all three now describe the masked contract and point unmasked detail at
`occ_tickets`. The claim that the `occ_tickets` index itself carries full names,
emails and `[internal]` notes was **kept** — it is still true, since
`scripts/index_occ_tickets.py` is deliberately out of scope.

### 3. MEDIUM-HIGH — `format_aggregate` destroyed the drill-down id (regression introduced by this change)

`_ENRICHED_ID_RE = re.compile(r"\s\(id [^)]+\)$")` required a leading space, but
`server._customer_display` emits a bare `"(id 9)"` with none. Verified through
the real `aggregate_tickets`:

```
1. [customer name withheld] — 2     # customer_id 9, resolve_user -> "Hans Müller"
```

The id is gone. That breaks the `aggregate_tickets` docstring instruction to
"feed a resulting `customer_id:<N>`" for exactly the rows where masking fired,
and contradicts `server.py`'s own comment that the id is appended "so rankings
still link to the customer-history drill-down". Root cause: two different
implementations of "already-enriched customer display" that disagreed on the
suffix shape.

Fixed: regex is now `\s*`, with a `not head` passthrough for the bare
`(id N)` form, plus tests at both the formatter and the full server path
(`test_server_aggregate_customer_withholds_a_resolved_name_but_keeps_its_id` —
the only pre-existing server aggregate test used a login-only user, so this
class of bug was invisible to the suite).

### 4. MEDIUM — the Art. 5(1)(c) framing overstated what was fixed

Article bodies, `Subject:` and ticket `title` are untouched, and
`group_by=title` ranks raw titles. A customer email signature alone carries name
and address:

```
--- article 1 j***@example.test/email from j***@example.test
Hallo, hier ist Hans Müller aus der Müller GmbH, meine Adresse ist jane.doe@example.test.
```

Masking free text would gut the demo rather than reduce it, so this is a design
choice — but the README claimed "none of it is necessary", which implied closure.

Fixed: reworded to "the structured identity and note fields below are masked",
and the residual is recorded explicitly in a new *Known limits of this mask*
section.

### 5. MEDIUM — `_mask_contact` masks by shape, not by role

`_mask_contact` keys on "looks like an email"; nothing in the Zammad payload
distinguishes staff from customer, and Zammad's `from` is frequently a *display
name* (Zammad's own article docs use `"from": "Christopher Miller"`). So the
same person's name can be withheld in `customer` and exposed in the article
header on the same screen.

Secondary, latent: `_mask_contact` did not strip an `(id N)` suffix, so
`_mask_contact("jane.doe@example.test (id 7)")` returned the address in full.
Unreachable from `_format_article` today; a trap if reused.

Fixed: the suffix trap (suffix now stripped before the email test, with a test).
The shape boundary is inherent to the data and is now documented as limitation 2
of the *Known limits* section rather than left implicit in a bullet that read
as a general rule.

### 6. MEDIUM — the override was unreachable in any deployed environment

`ZAMMAD_DEMO_UNMASKED_PII` appeared only in the zammad README. Not in the
compose `zammad-mcp` service, not in the Worker `Env`/`envVars`, not documented
in `wrangler.toml`. Enabling the demo needed a stack change, so requirement 2
("the demo must still look convincing") was not satisfiable from the docs, and
the accepted risk could not be audited from the running environment.

Fixed: forwarded through the compose service (default `0`), the Worker `envVars`
and `Env` (pinned by `env-vars-pin.test.js`), and documented in `wrangler.toml`.
Supervisord deliberately got **no** entry — `ZAMMAD_API_TOKEN`, `LITELLM_MASTER_KEY`
and `GROQ_API_KEY` all reach their programs by container-env inheritance, and a
hardcoded `0` there would have silently defeated the override.

Auditing: `run_mcp` now logs one startup warning naming the var when masking is
off, so the container log shows which mode it is in.

### 7. LOW-MEDIUM — the documented drill-down recipe stopped composing

`server.py`'s model-facing docstring and the README both instructed
`search_tickets(customer.email:<addr>)`. After masking, the model never sees an
address to substitute.

Fixed: the recipe routes `group_by=customer` → `customer_id:<id>` in the
README, in `server.py`, and in all three prompt copies.

### 8. LOW — PR body rendering check was stale

The body showed `--- article 1 jane.doe@example.test/email` under
"DEFAULT (masked)", contradicting its own table two paragraphs above.

Fixed: regenerated from the real formatter — see § Rendering check below.

### 9. LOW — two degenerate `id` renderings

`server._customer_display(x, None)` returned `x***@y.z (id None)`;
`enrich_rows(missing="?")` rendered as `[customer name withheld]`, implying a
name had been withheld when the lookup had merely missed.

Fixed: `_mask_customer` passes `?`, `-` and empty values through unchanged, so a
miss reads as a miss.

### 10. LOW — PR body cited the wrong file for `activityDetail: full`

Cited `apps/digichat/config/examples/occ-embed.yaml`, which says
`activityDetail: labels`; `full` is in
`docs/projects/online-compliance-center/README.md:60`.

Fixed: citation corrected in the PR body.

## Accepted limitations

Carried into the README rather than fixed, because each needs a product or legal
decision rather than a code change:

1. Article bodies, subjects and ticket titles stay unmasked.
2. `sender`/`from` masks by email shape; a customer display name can pass through.
3. `scripts/index_occ_tickets.py` still writes full customer names, emails and
   internal bodies into `occ_tickets`, which the OCC tenant fans out to on every
   question. That is a separate surface from the MCP formatters, out of scope for
   DIG-1063, and **not** covered by the demo override.

## Rendering check

Produced by running the real `format_ticket_detail` / `format_aggregate` against
a fixture whose article body carries a name and address and whose second article
is internal. This is also the honest picture of what the mask does **not** cover
(limitations 1 and 2).

**Default (masked):**

```
Ticket 515: Rechnung fehlt
State: open | Group: Vertrieb | Priority: 2 normal
Customer: j***@example.test | Owner: agent@sitaas.de
Created: 2026-10-01T09:12:00Z | Articles: 1

Articles (1):
--- article 1 (2026-10-01T09:12:00Z) j***@example.test/unknown from Jane Doe
Subject: Rechnung fehlt
Hallo, hier ist Hans Mueller, meine Adresse ist jane.doe@example.test.
... 1 internal note(s) omitted
--
Top customer by count (all visible; 5 ticket(s) scanned):
1. j***@example.test (id 7) — 4
2. (id 9) — 2
3. k***@sitaas.de — 1
Automation accounts (-, auto, jirasync@sitaas.de) are excluded from customer rankings.
```

**With `ZAMMAD_DEMO_UNMASKED_PII=1` (restores #4944):**

```
Customer: jane.doe@example.test | Owner: agent@sitaas.de
Created: 2026-10-01T09:12:00Z | Articles: 2
Note: Rueckruf nach Mittag vereinbart

Articles (2):
--- article 1 (2026-10-01T09:12:00Z) jane.doe@example.test/unknown from Jane Doe
...
1. jane.doe@example.test (id 7) — 4
2. (id 9) — 2
3. kunde@sitaas.de — 1
```

Note row 2 of the ranking keeps its `(id 9)` in **both** modes — that is
finding 3 fixed, and it is what keeps the drill-down executable.

## What the reviewer confirmed as genuinely sound
`_mask_customer` fails closed on everything thrown at it (`ü***@ö.de`,
`a@b@c.test`, `Jane Doe <jane.doe@example.test>`, `jane@localhost`, whitespace,
`None`, `""`, `-`, `7`, `007`, `-7`). Two-layer masking is idempotent for the
email case. Override parsing accepts no value that merely *looks* truthy.
The override restores the #4944 rendering exactly. `format_aggregate` gating on
`group_by == "customer"` is the right narrow scope — owner rankings keep
resolved staff names.
