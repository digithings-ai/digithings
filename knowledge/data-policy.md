# digithings client data and data protection policy

One page. What we keep, how long, which models may see it, what is anonymised, how deletion works, who may touch it.
Written by Counsel with Security, 2026-10-05. Decision owner: Chris.

**Revision 2, 2026-10-05.** Revision 1 was Counsel's opinion about four controls nobody had verified. Security
answered all four on [DIG-567](/DIG/issues/DIG-567) from the systems, and **this revision folds those answers in
verbatim**. Chris has answered every open decision; they are recorded in §11. Where Security wrote
**not implemented**, this page says not implemented. Where Security wrote **cannot tell**, this page keeps
UNKNOWN. None of those gaps have been softened.

**Status: ADVICE with Security's verified findings folded in. This page is not a compliance record and it does
not by itself satisfy any GDPR obligation.**

**What changed from revision 1, in one line: it reads worse, because it is truer.** Revision 1 asserted four
controls; Security found **one does not exist**, **one is the wrong kind of control**, and of the three UNKNOWNs,
**one is known-broken**. Two claims in revision 1 were simply wrong and are corrected below. Nothing was
improved, softened or substituted.

Client is referred to by codename only. **twelve-x stays anonymous in every artefact, including this one.**

---

## 0. The findings that matter most

**0.1 — We cannot certify the models the task named.** DIG-163 asked that client data go to "zero-retention models
only: Space Bunny, LongCat". **Neither is in our retention catalogue.** `docs/providers/snapshots/` holds a
`data_privacy` block per provider — `trains_on_free_tier`, `retention_days`, `zero_retention_on_paid`,
`gdpr_compliant`, `soc2`. Space Bunny and LongCat have no snapshot file, so **we hold no retention record for
them at all** and they cannot be listed as approved here. CONFIRMED by repo search 2026-10-05.

By that same catalogue, `zero_retention_on_paid: true` is recorded for **mistral, gemini, and openai (only with
the zero-data-retention add-on)**. All twelve other providers record `false`. CONFIRMED.

**0.2 — Zero retention does not authorise the transfer.** A zero-retention provider still *receives* the personal
data. If the provider is outside the EU/EEA, sending it client data is a restricted transfer that needs a Chapter V
mechanism regardless of how briefly the provider keeps it:

> "Any transfer of personal data which are undergoing processing or are intended for processing after transfer to
> a third country or an international organisation shall take place only if, subject to the other provisions of
> this Regulation, the conditions laid down in this Chapter are complied with by the controller and processor…"
> — **GDPR Art. 44(1)**. CONFIRMED as to substance.

Of our three zero-retention providers, **the provider's country of establishment decides whether a Chapter V
mechanism is needed at all** — and **our own catalogue records no domicile field for any provider.** The
snapshots carry `provider`, `last_checked`, `source`, `free_tier`, `paid_tier`, `capabilities`, `data_privacy`,
`reliability`, `verification`, `notes` and nothing about where the company is incorporated. CONFIRMED by schema
read 2026-10-05.

So I am **not** asserting which of the three is EU-established. What I can say:

- Mistral publishes **EU-specific terms** as a separate document from its ROW terms, and our own free-provider
  note calls the paid tier "Strong European data sovereignty option". That is consistent with EU establishment.
  **LIKELY, not CONFIRMED** — I did not find the incorporating legal entity named in the Terms landing page,
  and a Terms page is the wrong place to be certain of a corporate fact.
- Google offers EU data residency on some Vertex AI products, so "US vendor" is not by itself a sufficient
  test either. **The test in the GDPR is establishment, not nationality.**

**The rule that actually governs is therefore:** a provider is approved for client personal data only if it is
**EU/EEA-established, or we have an Art. 46 mechanism in place before sending.** Zero retention satisfies neither.
**We have no record of an Art. 46 mechanism for any provider.** UNSURE whether one exists outside the repo.
**Chris has ordered the Article 46 work now** — see §11. That decision does not make the mechanism exist today, so
this paragraph still stands as written.

**0.3 — Free tiers train on data.** The snapshots record `trains_on_free_tier: true` for Mistral and others. A
free-tier key pointed at client correspondence is provider training on client personal data. **Prohibited here,
no exceptions.** CONFIRMED by catalogue read 2026-10-05.

**0.4 — Security answered the four controls revision 1 had only asserted.** Security's summary, verbatim:
**one of the four claims is unimplemented, one is real but the stated control is the wrong one, two of the three
UNKNOWNs are now resolved and one is known-broken.** Detail is in §2 (Article 9), §5 (pseudonym key), §6
(deletion), §7 (access). Read those sections as findings, not as plans.

Two claims in revision 1 were **wrong** and are corrected here:

- Revision 1 said we "log the pseudonym key separately, access-controlled". **There is no pseudonym key.** No key,
  no map, no code, in any store or codebase. §5.
- Revision 1 said `.gitignore` anchoring of `projects/*` is "the control to rely on". It is a commit-prevention
  control. **Any agent can read every `projects/*` client file today.** §7.

---

## 1. What we keep

| What | Why we hold it | Lawful basis | Confidence |
|---|---|---|---|
| Client exports (chat logs, email threads) | Feeding the client's own agents | **Now `controller` per Chris (§11).** Where we act only on the client's instructions, Art. 28 processor terms apply instead | DECIDED as controller; the processor/processor split is **UNRESOLVED** per dataset |
| Derived agent artefacts (summaries, embeddings, thread state) | Same | Same | Same as above |
| Run logs and traces | Debugging, incident reconstruction | Legitimate interests — **Art. 6(1)(f)** | LIKELY |
| Provider-side logs (what a model vendor received) | We cannot hold these | n/a | CONFIRMED we do not hold them |
| Anything about **our** people (Chris, staff, contractors) | Payroll, invoices, tax | **Art. 6(1)(c)** legal obligation | CONFIRMED — Italian tax law |

The distinction in row 4 is the one we keep getting wrong. **A zero-retention vendor holds nothing after the call.
That does not mean we hold nothing** — we hold the prompt, the response, and the run record on our side, and those
contain the client's data. Deletion on our side has to be argued separately from deletion at the vendor.

**This is all personal data.** Art. 4(1): "'personal data' means any information relating to an identified or
identifiable natural person ('data subject')". CONFIRMED. An email thread is personal data line by line; the
*business* content around it does not stop it being personal data.

## 2. Client correspondence will contain Article 9 data and we cannot currently filter it

> "Processing of personal data revealing racial or ethnic origin, political opinions, religious or philosophical
> beliefs, or trade union membership, and the processing of genetic data, biometric data…, data concerning health
> or data concerning a natural person's sex life or sexual orientation shall be **prohibited**."
> — **GDPR Art. 9(1)**. CONFIRMED.

**Any inbox contains health, opinion and belief content.** Art. 9(1) is a prohibition with narrow exceptions
(Art. 9(2)), not a permission. **There is no Article 9 detection, classification or redaction capability anywhere
in our pipeline, in any path, including agent ingestion.** CONFIRMED by Security on
[DIG-567](/DIG/issues/DIG-567), run `3ef5184a`, against the monorepo at `9bee32091`.

This is the most serious operational gap in this page, and it is worse than the retention question: a retention
period bounds how long we hold Art. 9 data, but with no filter we may be *collecting* it without an exception in
the first place. **Reading a client's whole inbox is a bigger legal step than reading a support ticket.**

**Correction to revision 1, and it is the other way round from what you would expect.** Revision 1 said "no
redaction exists anywhere". Security's answer: the Article 9 claim **holds**, but the wider wording was not
accurate. **Two secret-oriented redactors exist. Neither is Article 9 and neither is on an ingestion path.**

| What exists | What it does | Where it is bound | Live? |
|---|---|---|---|
| `digitrace/src/digitrace/redaction.py` — `PiiRedactor` / `default_redactor()` | Exactly three regexes: API key (`sk-`, `sk_`, `dgk_live_`, `dgk_test_`, `lsv2_`), email, phone → `[REDACTED_KEY\|EMAIL\|PHONE]`. **Zero Article 9 categories** — no health, biometric, genetic, racial/ethnic, political, religious, union, sex-life or sexual-orientation patterns. Extensible via `DIGI_PII_PATTERNS` | **LangSmith egress leg only** — the sole wiring is `digitrace/src/digitrace/trace.py:111` | **No. Inert.** Requires `LANGSMITH_API_KEY`, which is unset, so `tracing_enabled()` is False and the leg no-ops. **Redaction never executes today** |
| `digibase/src/digibase/audit.py` — `redact_mapping()` | Key-**name**-based match on `password`, `api_key`, `token`, `secret` → `[REDACTED]`. **Secret redaction, not PII and not Article 9.** The connector's own docstring warns a key-name redactor cannot scrub secrets that appear in *values* | `digibase.audit.emit_event()` audit JSONL only | Yes, for that one stream |

**The operative sentence for the board:** no Article 9 detection, classification or redaction exists in any path,
including agent ingestion. Two secret-oriented redactors exist — `digitrace` (API key, email, phone; LangSmith
egress only; currently disabled because `LANGSMITH_API_KEY` is unset) and `digibase.audit` (key-name based, audit
JSONL only) — and neither detects or masks any Article 9 category.

If one exists but is not wired into ingestion, that is a different and more actionable finding. Both of these are
exactly that case. `digitrace/AGENTS.md` records the Phase 2 PII-redaction middleware as **deferred to roadmap**,
so the gap is known to the owning team rather than a surprise.

## 3. How long

**No retention period was set anywhere in our files before this page.** CONFIRMED by repo search. Art. 5(1)(e)
requires:

> "Personal data shall be … kept in a form which permits identification of data subjects for **no longer than is
> necessary** for the purposes for which the personal data are processed."
> — **GDPR Art. 5(1)(e)**. CONFIRMED.

**Chris has now chosen the periods. He answered `90 days for records, 30 days for chat and email` on
2026-10-05.** These are his decisions, not Counsel's proposal:

| Dataset | Retention, as decided | Basis for the cutoff |
|---|---|---|
| Client exports (chat logs, email threads) | **30 days** after the contract ends | The purpose ends with the contract |
| Agent-derived artefacts (summaries, embeddings, thread state) | **30 days**, same as the source | No point outliving the source |
| Run logs, traces, audit and run records | **90 days** | Enough to debug and reconstruct; Art. 22 automated-decision risk drops once the trace is gone |
| Invoices, contracts, tax records | **10 years** | Italian civil/fiscal retention; Art. 17(3)(b) and (e) exceptions — legal obligation and legal claims. **Not ours to shorten.** |

**The 90-day trace retention is also what keeps us clear of Art. 22.** Art. 22(1) gives a data subject the right
"not to be subject to a decision based solely on automated processing, including profiling, which produces legal
effects… or similarly significantly affects him or her." CONFIRMED. Short trace life is not a full answer to
Art. 22, but it bounds it.

**These are chosen periods, not periods we can yet enforce.** Two stores are unbounded today, and §6 sets out
which. A retention period we do not run is not a retention period. Security found **no retention or rotation code
anywhere for the audit log**, and **no pruning at all for `refs/backup/**`**. Read the two tables together.

**Deletion is not promised to any client in a contract.** Chris answered `No promise in the contract yet — close
the gaps first`. That is the right answer on the evidence in §6, and it holds until the three gaps close. Do not
put a deletion guarantee in a contract.

## 4. Which models may see client data

**Rules, in order of application:**

1. **Only providers with `zero_retention_on_paid: true` in our own catalogue** — currently mistral, gemini,
   openai-with-ZDR-add-on. A model absent from `docs/providers/snapshots/` is **not approved**, regardless of what
   anyone believes about it.
2. **Paid tier only.** Free tiers train on data (§0.3).
3. **EU/EEA-established provider only, unless an Art. 46 mechanism is in place first, and the client has agreed
   in the contract.** Domicile is unrecorded in our catalogue for every provider (§0.2), so on today's evidence **no
   provider is yet affirmatively approved under this rule.** Treat the candidate list as Mistral paid, pending the
   entity check. Chris has ordered the Art. 46 work (§10) and has made the contract clause a condition; **neither
   exists yet.**
4. **No client data on a model we cannot name in the catalogue.** This currently excludes Space Bunny and LongCat
   (§0.1). They may well have acceptable terms — **we have not checked, and "not checked" is not "approved".**
5. **twelve-x and all client codenames are pseudonymised before any prompt leaves our infrastructure** (§5).

**Rule 5 has no implementation behind it.** Security confirmed on DIG-567 that **no pseudonymisation exists
anywhere** — no key, no map, no code. So rule 5 today is an instruction that cannot be followed, and any job that
claims to have satisfied it is mistaken. See §5.

**Chris has seen this and accepted the exposure knowingly** (`model_layer: accept_exposure`, 2026-10-05). Read
exactly what that decision is and is not. It is: *we know no provider clears rule 3, and we are choosing to
proceed anyway on the record.* It is **not** an approval of any provider, and it does **not** make rule 3 met.
Rule 3 turns on EU/EEA establishment or an Art. 46 mechanism. Zero retention satisfies neither. The decision
changes who owns the risk, not whether the rule is satisfied.

**On today's evidence rule 3 is unmet for every provider, so the honest position is that no job may yet send
client personal data to any external model.** That is uncomfortable and it is the accurate reading of what our
artefacts support. It is a gap to close this month, not a reason to guess.

**If these rules cannot all be satisfied for a job, the job needs a decision from Chris — not a workaround.**
That is the honest reading of Art. 5(1)(b) purpose limitation and Art. 5(1)(c) data minimisation together.

## 5. What gets anonymised before anything goes to another model

**Read this section as a plan, not a description.** Security verified on DIG-567 that **no pseudonymisation exists
anywhere in our systems.** Nothing in this section happens today. It is written as the design we intend to build,
because writing it as current fact was one of the two errors in revision 1.

Data protection by design is a legal duty, not a nicety:

> "…the controller shall, both at the time of the determination of the means for processing and at the time of
> the processing itself, implement appropriate technical and organisational measures, **such as
> pseudonymisation**, which are designed to implement data-protection principles, such as data minimisation, in
> an effective manner…"
> — **GDPR Art. 25(1)**. CONFIRMED.

> "…appropriate technical and organisational measures to ensure a level of security appropriate to the risk,
> including inter alia as appropriate: **the pseudonymisation and encryption of personal data**…"
> — **GDPR Art. 32(1)(a)**. CONFIRMED.

**Applied to us, before a prompt leaves the infrastructure:**

**NOT IMPLEMENTED. There is no pseudonymisation in our systems, so there is no pseudonym key to keep.**
Security answered this on DIG-567, run `3ef5184a`, against the monorepo at `9bee32091`, and the answer is
categorical. Security's own words:

> There is no pseudonym key. Not in Keychain, not in Bitwarden, not in any log.

What Security actually did to establish that: an exhaustive `rg -i "pseudonym"` across the monorepo with
`--no-ignore --hidden`. The only first-party hit is this policy file itself. All 29 other hits are vendored
third-party code (`cryptography`, `pypdfium2`, OpenTelemetry semconv, `pyasn1_modules`) and copies of the same
venvs in worktrees. A wider search for `de-?identif|token_?map|codename_?map|anonymi[sz]` produced two false
positives — a Chroma `anonymized_telemetry=False` flag and a script docstring. The design intent exists in three
documents and one SQL migration; **no code implements it.** `dt-keys list` shows exactly two secrets under the
`digithings` service: `opencode-go` and `backup-key`. No pseudonym entry.

**So revision 1 of this page was wrong**, in the direction that matters. It said we "log the pseudonym key
separately, access-controlled". That described **a control we do not operate.** The answer to Counsel's original
question — is the key in the same log, or in the same store — is that there is **no key and no pseudonymised
data, because no pseudonymisation exists anywhere.** A custody regime is **not applicable: there is nothing to
place in one.**

The Art. 25(1) reasoning above is sound *as a design*. It must not be published as present-tense fact. Until
someone writes the code, §4 rule 5 and this section describe what we intend to do, not what we do.

**What would make this real.** Three things, and the middle one is the one usually skipped:

1. A key that exists: generate the per-run token map, store it in a place with its own access rule.
2. **A key whose custody is a control, not a sentence.** A key in the same log as the tokens it decodes is
   decoration. Real custody means separate store, separate access path, audited retrieval, and a named owner.
3. A rotation story, so the key's blast radius is bounded and old runs cannot be re-identified by anyone who
   obtains it.

| Do | Do not |
|---|---|
| Replace personal names with stable per-run tokens | Send real names "because the model needs context" |
| Strip email addresses, phone numbers, account and payment identifiers | Send a thread with the address headers intact |
| Replace employer and client names with codenames | Send `twelve-x` or a client name in any prompt |
| Drop attachment bodies not needed for the task | Bulk-embed an inbox |
| **Plan:** keep the pseudonym key in a separate store from the tokens, access-controlled | Put the pseudonym key in the same log |

**The last row is the plan, not the current state.** Revision 1 presented it as what we do. It is what we would
need to do.

**Limitation, stated plainly:** pseudonymisation is a security and minimisation measure, **not an exit from the
GDPR.** Recital 26 treats pseudonymised data as still personal data. Anonymised data is out of scope; we do not
currently claim to produce it. The Art. 32 question is now closed rather than open: **UNKNOWN became worse than
UNKNOWN.** Revision 1 asked whether our key storage met the Art. 32 standard. The answer is that there is no key
storage to assess.

## 6. How deletion works

**The data subject's right is absolute in form and qualified in substance.** Art. 17(1)(a) CONFIRMED: erase where
"the personal data are no longer necessary in relation to the purposes for which they were collected or otherwise
processed". Two exceptions matter to us: Art. 17(3)(b) legal obligation, and Art. 17(3)(e) legal claims — the
tax and invoice rows in §3.

**Deletion must reach every place a copy can sit. Security verified all of them on DIG-567** (run `3ef5184a`,
monorepo at `9bee32091`). Revision 1 left three of them as UNKNOWN. **Two are now resolved and one is
known-broken.** Nothing below has been rounded up.

| Where | Status, as verified |
|---|---|
| The export file | **CONFIRMED** — it is a file, so it can be deleted |
| Our derived artefacts | **CONFIRMED** — files, deletable |
| Thread state in the database | **RESOLVED — works.** Owner-scoped delete cascades to messages and quant runs |
| The browser's own copy of the thread | **SURVIVES deletion.** Full message text sits in `window.localStorage` |
| Embeddings / vector index | **KNOWN-BROKEN — HTTP 501, "not implemented for this digisearch deployment"** |
| Backups — tarball archives | **PARTIAL** — `dt-backup prune` deletes archives older than `KEEP_DAYS` |
| Backups — `dt-snapshot` git refs | **UNBOUNDED. No pruning exists at all** |
| Audit JSONL log | **UNBOUNDED.** No retention or rotation code anywhere |
| Provider-side copies | **Out of our hands** — mitigated only by zero retention (§0.1/0.2) |

### What works

**Thread state deletes properly, and the deletion is scoped.** `apps/digichat/src/app/api/conversations/[id]/route.ts:107`
runs `DELETE` behind `requireDigiChatAuth`, resolves the tenant, and calls
`deleteConversation(db, {conversationId, tenantId, ownerUserSub})`. The delete is
`apps/digichat/src/lib/conversations-repo.ts:194`, scoped
`WHERE id AND tenant_id AND owner_user_sub` — so one owner cannot delete another's thread. Messages and quant
runs follow by database cascade: `apps/digichat/src/db/schema.ts:96` and `:75` both declare
`onDelete: "cascade"`, and the applied SQL agrees — `drizzle/0001_conversations.sql:18` and
`drizzle/0002_quant_runs.sql:12` both carry
`FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE cascade`. That is a
genuine cascade, not an application-level best effort. CONFIRMED.

### What survives deletion anyway

**The browser keeps a full copy of the messages.** `apps/digichat/src/lib/thread-local.ts:54` `saveLocalThreads()`
persists `id, title, updatedAt, messages` — **the full message text** — to `window.localStorage` under a
per-owner key, rewritten on every mutation. `chat-shell.tsx:275` `deleteThread` filters the local state and
re-saves, but line 278 only fires the server `DELETE` when `t?.remote && serverPersistence`. So a **local-only
thread never reaches the server at all**, and localStorage is outside any server-side erasure path regardless.
Deleting the thread in the UI is not deleting the data.

### What is explicitly not implemented

**Embedding deletion returns HTTP 501.** `digisearch/src/digisearch/server.py:1674` exposes
`DELETE /indexes/{name}/documents/{doc_id}`, its docstring reads "Delete document from index (not implemented.)",
and the handler raises `HTTPException(status_code=501, detail="Per-document delete is not implemented for this
digisearch deployment")`. The primitives exist and are unreachable: `digisearch/src/digisearch/indexes/base.py:27`
declares `delete(ids)`, implemented at `chroma.py:321` and `vectorize.py:230`, and
`digisearch/src/digisearch/retrieval/pgvector.py:383` calls a separate pgvector store. **`azure_search.py` has no
`delete` method at all.** So this is `not implemented`, the reason was written by the authors, **and nobody runs
it because nobody can.** An embedding index of client content cannot be erased on request today.

### Backups: partly age-based, and the rest unbounded

**The tarball path does have retention.** `dt-backup prune` → `cmd_prune()` at line 261 removes local
`dt-backup-*.tar.gz.enc` archives older than `KEEP_DAYS`, and lines 273–304 run a remote prune via
`rclone delete --min-age ${KEEP_DAYS_REMOTE}d` (which requires `rclone` to be installed). That is
**archive-level and age-based, and it does not touch git refs.**

**Nothing deletes a file from a `dt-snapshot` commit.** Security searched `dt-snapshot`, `dt-backup` and
`dtlib.py` for `prune|gc|expire|ttl|update-ref -d` and found **none of them in `dt-snapshot`**. Its only
commands are `run`, `check PATH`, `ledger`. There is no ref expiry, no TTL, no retention policy.
`refs/backup/**` therefore accumulate without bound — **83 locally**, and **74 of them pushed to the `github`
remote**.

The good news, and it is good: **snapshot trees currently contain no client data.** `snapshot_commit()` in
`/Users/chrisstefan/paperclip-workspace/kit/bin/dt-snapshot` builds each commit from the whole working tree via a
temporary `GIT_INDEX_FILE` (`read-tree HEAD` → `add -A` → `write-tree` → `commit-tree -p HEAD`). `add -A`
respects `.gitignore`, and `/projects/*` is ignored, so client data is not captured. Security verified this
across **all 83** local backup refs: the only `projects/` path in any of them is `projects/README.md`. The newest
backup tree holds 4,270 files, exactly one under `projects/`.

The bad news: **that is a property of `.gitignore`, not a control** — the same weakness as §7. If one client file
ever reaches a tracked path, it enters every subsequent snapshot, and deleting it from the working tree changes
nothing. And `dtlib.push_remote()` matches `pushBackupsFor = ["github.com/digithings-ai/", "github.com/chrizefan/"]`
and pushes `{sha}:{ref}` for each snapshot. `gh repo view digithings-ai/digithings` returns
`{"visibility":"PUBLIC"}`. **So 74 snapshot commits are fetchable and clonable by anyone on the internet today**,
under `refs/backup/**` — not on `refs/heads`, so invisible to ordinary browsing. They hold no client data now,
but they are a standing egress channel for everything tracked, **and secret history has already passed through
them**: existing backup refs are named for DIG-179 ("live-proton-mailbox-password-is-committed-in-plain-text")
and DIG-41 ("apply-credential-scrub"). Security filed **DIG-784** for this.

**A third unbounded store.** `digibase.audit.emit_event` appends to `AUDIT_LOG_PATH` (default
`digiquant/results/audit/events.jsonl`; 1.16 MB on disk). **No retention or rotation code exists anywhere** —
`rg AUDIT_LOG_PATH` hits only docs and compose. The optional `AUDIT_SINK_URL` also POSTs each line to an
external sink, fire-and-forget with failures swallowed, so it doubles as an egress switch.

### The conclusion, unchanged from revision 1

**A deletion that does not account for snapshots is not a deletion.** Revision 1 flagged that and called it
UNKNOWN. **It is worse than unknown — it is confirmed and unbounded.** Chris's decision not to promise deletion
in a contract until the gaps close was the right call, and on this evidence the gaps are three, not two.

**Two of the three things revision 1 called UNKNOWN are now resolved and one is known-broken**, which is a
better position than ignorance even though it reads worse. Nothing here has been softened.

## 7. Who may touch it

Revision 1 said the `.gitignore` rule "is the control to rely on, not an assumption". **Security verified that
claim on DIG-567 and it does not hold as stated.** `.gitignore` prevents a commit. It does not prevent a read,
and this section is about reads. Corrected below.

- **Chris** — client data of his own clients, as the party who signs.
- **Named engineers on that engagement only** — least privilege, per Art. 32(1)(b) CONFIRMED
  ("the ability to ensure the ongoing confidentiality… of personal data").
- **Agents** — only on pseudonymised data, per §5. **In practice agents are not pseudonymised, because nothing
  pseudonymises them (§5).**
- **OSS Researcher and contractors** — **no access to `projects/*` client data.**
- **Not Security's problem to hold a copy.** Technical controls are queried without exporting the data.

### What `.gitignore` actually enforces

**It works, and only as commit prevention.** `.gitignore:41` is `/projects/*` and `:42` is
`!/projects/README.md`. The anchoring is deliberate — lines 39–40 and 148–150 record the rationale, and ADR-0006
reserves `docs/projects/` for public dogfood, so an unanchored `projects/` would be a trap. `git check-ignore -v
projects/sitaas` matches `.gitignore:41`. `git ls-files projects/` returns **one file, `projects/README.md`**,
and `git status --porcelain --ignored projects/` confirms `local/`, `sitaas/`, `twelve_x/`, `v-simple.md` and
`twelve_x.egg-info/` are all ignored. No CI workflow references or copies `projects/` — `rg projects
.github/workflows/` hits only GitHub Projects-board URLs — and no preflight copies client paths. That much is
sound.

### What is not enforced

**Every agent in this company runs as the same unix user, `chrisstefan`.** `/Users/chrisstefan/Code/digithings/projects`
is `drwxr-xr-x` — world-readable — and holds `README.md`, `local/`, `sitaas/`, `twelve_x/`,
`twelve_x.egg-info/` and `v-simple.md`. Security's direct answer to the question this page should have asked:

> Yes — a non-engagement engineer can read all `projects/*` client data today, on any issue, with no tool or
> permission required.

The only thing in the way is a sentence in the root `AGENTS.md` — "`projects/` is confidential — never push to
public remotes." **That is a convention, not a control.** A convention is worth having. It is not Art. 32(1)(b)
"the ability to ensure the ongoing confidentiality", because nobody has demonstrated the ability.

**Enforcement would need one of:** per-engagement file permissions; a separate account or OS ACL per engagement;
or a path-guard in the agent runtime that refuses reads outside the current engagement's allowlist. Any of the
three is a real change. Security filed **DIG-785** to own it.

### Client data is already in git history

**`.gitignore` cannot un-track anything.** Commits `6e9cd9cc9` and `1dbd3db74` still carry `projects/` paths and
**are reachable from many branches**, so that content is in any clone. Commits `1a657079c`, `18cd7c997` and
`b8c1b76d8` (the Twelve X FX research project) are **unreachable from any branch** and therefore dangling — but
the object blobs still exist locally and stay recoverable until `git gc` prunes them. **Client data is in repo
history today.**

### The credential scanner is muted on that same path

`.gitleaks.toml:39–42` allowlists `'''^projects/[^/]+/vault/'''`, commented "confidential research vaults … never
pushed to public remotes". The effect is that **gitleaks will not report a credential committed inside a
`projects/*/vault/` file.** And `.gitignore` does not reduce gitleaks' scan surface — `gitleaks dir .` still
reports credentials inside ignored directories — so gitleaks was never an access boundary in the first place.
**The one client path that is unguarded by permissions is also muted in credential scanning.** Both halves of
DIG-785.

**Copies outside the repo: none.** Security searched agent workspaces under
`~/.paperclip/instances/default/workspaces` and `~/.dt-scratch-h5`; there is no `sitaas`, `twelve_x` or
`twelve-x` directory anywhere outside the monorepo, only two incidental text mentions in a ledger config and a
repository-janitor review.

### The snapshot boundary, restated

Snapshot scope is wide. `dt-snapshot` walks `cfg["roots"]` (default `~/Code`) **and** `cfg["agentWorktreeRoots"]`,
and the live `~/.config/digithings/kit.json` sets those roots to
`["~/.paperclip/instances/default/workspaces", "~/Code/digithings/.paperclip/worktrees"]`.
`~/.config/digithings/snapshot-state.json` lists **31 repos** — all under `~/Code` and Paperclip worktrees,
including `digithings`, `twelve-x`, `apollo`, `datatapap-web`, `gaia`, `stack-deploy-main`, ~13 `digithings-wt-*`
and ~13 `.paperclip/worktrees/DIG-*`. (`digithings-books` is not in the set; it has no git remote at all.) **Every
one of those is inside the snapshot blast radius**, which is exactly why the `.gitignore` property in §6 is
load-bearing and fragile at the same time.

## 8. Three obligations we do not currently meet

These are not policy gaps. They are missing artefacts.

**8.1 — No record of processing activities.** Art. 30(1) CONFIRMED: "Each controller and, where applicable, the
controller's representative, shall maintain a record of processing activities under its responsibility." The
small-organisation exemption in Art. 30(5) applies only where processing is **occasional**, or **low-risk**, or
does not include Art. 9 data. Reading clients' correspondence routinely is none of those three. **The exemption
is unavailable and we need the record.** LIKELY.

**8.2 — No privacy notice, and we now know it is ours to give.** Art. 13(1) CONFIRMED requires the controller to
give the data subject identity and contact details, purposes, legal basis, recipients, retention period and
data-subject rights "at the time when personal data are obtained". **Chris has decided we are a `controller` — "we
determine our own purposes" (2026-10-05).** So the notice is **our** obligation, not the client's, and we owe one
and have none. This used to turn on Decision 1. It does not any more; the decision made it ours.

**8.3 — No DPIA, and one may be required.** Art. 35(1) CONFIRMED requires an impact assessment *before* processing
where it "is likely to result in a high risk", having regard to "the nature, scope, context and purposes of the
processing". Routinely reading clients' email, on a public AI platform, with Art. 9 content and international
transfers, is a plausible high-risk case. **We should assume a DPIA is required before the next client dataset
lands, not after.** LIKELY, not CONFIRMED — this needs a real risk assessment, not my reading of one clause.
**Security's findings make this worse, not better:** Art. 9 content arrives unfiltered (§2), access is
unenforced (§7), and two stores are unbounded (§6). Each of those is a risk the DPIA would have to score.

## 9. Breach

- **Art. 33(1)** CONFIRMED: notify the supervisory authority "without undue delay and, where feasible, **not
  later than 72 hours** after having become aware of it", unless the breach "is unlikely to result in a risk to
  the rights and freedoms of natural persons". Art. 33(2) CONFIRMED: if late, give reasons.
- **Art. 33(3)** CONFIRMED: "**The processor shall notify the controller without undue delay** after becoming
  aware of a personal data breach." **This is a clock on us, and it is short.** If we are processor, the 72-hour
  clock is the client's, but *our* duty to tell them starts immediately and "without undue delay" is not "next
  business day".
- **Art. 34(1)** CONFIRMED: where the breach "is likely to result in a high risk", the controller "shall
  communicate the personal data breach to the data subject without undue delay". A high-risk breach involving
  client correspondence is not unlikely to reach this threshold.

## 10. Transfer to a model provider, stated as the rule

Combining §0.2 and §9: the sequence for any new client dataset is **(1)** confirm the provider is EU-based, or put
an Art. 46 mechanism in place first; **(2)** confirm zero retention on the paid tier; **(3)** pseudonymise per §5;
**(4)** record it under Art. 30. **Sending first and documenting later is the failure mode this page exists to
prevent.**

**Step 1 is where we stop today, and steps 2 and 3 are both unbacked.** No provider is EU-established on our
evidence (§0.2). No pseudonymisation exists (§5). Security's answers **do not satisfy step 1**: Art. 44(1) turns
on establishment or an Art. 46 mechanism, **not on zero retention.** A provider that keeps nothing is still a
provider the data was transferred to.

**Chris has chosen to do the Article 46 work now** (`art46_gap: do_it_now`, 2026-10-05). That is the only path in
this sequence that can be completed without a provider's cooperation, and it is the right priority. **Until it
exists, step 1 remains unmet and §4 rule 3 remains unmet for every provider.** Chris also answered that
transfers are permitted **"only where the client agrees in the contract"** — so the Art. 46 mechanism and the
contract clause have to be built together, not separately.

**What the Article 46 work actually is.** Art. 46 permits a transfer on the basis of an adequacy decision, or
appropriate safeguards, or a derogation. The realistic candidates here are the **EU Standard Contractual Clauses**
under Art. 46(2)(c), signed by the provider, plus a transfer impact assessment to support Art. 46(1)'s
requirement that the controller "shall take the necessary measures to ensure that the level of protection of
personal data is not undermined". **CONFIRMED** that this is the mechanism family; **UNKNOWN** whether any
candidate provider will sign, because that has not been asked. Counsel's view: ask Mistral, in writing, before
building anything else — a signed SCC set from one provider is worth more than a completed questionnaire from three.
That work is not yet done and this page does not pretend otherwise.

---

## 11. What Chris has decided, and what is still open

### Decided, 2026-10-05

| Question | His answer | What it settles |
|---|---|---|
| **In what capacity do we hold client data?** | **`controller`** — "we determine our own purposes" | Art. 28 processor terms no longer cover the whole picture. **Art. 13 notice is ours to give (§8.2).** The Art. 30 record is ours. |
| **May client data leave the EU/EEA?** | **`yes_client_agrees`** — "yes, but only where the client agrees in the contract" | Transfers are allowed *conditionally*. Two obligations follow: build the Art. 46 mechanism, **and** add the contract clause. Neither exists yet (§10) |
| **Do we offer a deletion commitment?** | **`no_commitment`** — "no promise in the contract yet — close the gaps first" | Correct on the evidence. §6 confirms three gaps, not two. **Do not put a deletion guarantee in any contract** |
| **Retention periods** | **`d90_30_split`** — "90 days for records, 30 days for chat and email" | §3 is now decided, not proposed. **But not yet enforceable** — two stores are unbounded |
| **The Article 46 work** | **`do_it_now`** — "yes, do the Article 46 work now" | The only unblockable step in §10's sequence. Own it as a project |
| **Working files on disk** | **`accept_now`** — "accept the gap for now — record it as a known risk" | §7's unenforced access boundary is **accepted knowingly**, not fixed. It stays on the register as a live risk |
| **Sending client data to a model that fails §4 rule 3** | **`accept_exposure`** — "accept the exposure knowingly" | Ownership of the risk sits with Chris. **It does not make rule 3 met** (§4) |

### Still open

- **What do we do with the personal data of people who are not the client?** Client correspondence routinely
  contains third parties' data. The model provider's Terms make **the person using the service** the
  contracting party, and no digithings account exists — so the counterparty would be **Chris personally**, an
  Italian resident litigating in Delaware under JAMS. Pending card `03401674`. Counsel flagged that contracting
  through the business **may touch the Italian forfettario tax position** and will not move on that without
  Chris's explicit approval.
- **Whether any candidate provider will sign Art. 46 safeguards.** Not asked yet (§10).

**On the two he accepted rather than fixed** — the working-files gap (§7) and model-layer exposure (§4) — the
honest reading is that they are now **known, accepted risks with a named owner**, which is a legitimate place for
them to be. They are not fixed, and this page does not imply they are.

---

## Confidence and sourcing

| Claim | Label | Source |
|---|---|---|
| Art. 4(1) definition; Art. 5(1)(e) retention; Art. 9(1) special categories; Art. 13; Art. 22; Art. 25(1); Art. 28; Art. 30; Art. 32; Art. 33; Art. 34; Art. 35; Art. 44; Art. 46 | **CONFIRMED** as to substance | GDPR 2016/679 text, article-by-article, retrieved 2026-10-05 |
| Which providers record zero retention | **CONFIRMED** | `docs/providers/snapshots/*.yaml`, read 2026-10-05 |
| Mistral is EU-established | **LIKELY** | EU-specific terms exist at `mistral.ai/terms`; `docs/free-providers/mistral.md:27`. Incorporating entity not found — needs the DPA |
| Domicile of **any** provider is recorded in our catalogue | **CONFIRMED that it is not** | Snapshot schema has no country/establishment field |
| Free tiers train on data | **CONFIRMED** | `trains_on_free_tier: true`, snapshots |
| No Art. 9 filter in our pipeline | **CONFIRMED** | Repo search, 2026-10-05 |
| No retention period anywhere in our files | **CONFIRMED** | Repo search, 2026-10-05 |
| Space Bunny and LongCat have no retention record | **CONFIRMED** | No snapshot file exists for either |
| Controller vs processor status | **DECIDED** | Chris, `capacity: controller`, 2026-10-05. No longer an inference |
| Art. 30(5) exemption unavailable | **LIKELY** | Turns on whether processing is occasional/low-risk |
| A DPIA is required before the next dataset | **LIKELY** | Turns on a real risk assessment, not this page |
| **A pseudonym key exists and is access-controlled** | **CONFIRMED THAT IT DOES NOT EXIST** | Security, DIG-567 run `3ef5184a` at `9bee32091`: exhaustive `rg -i "pseudonym" --no-ignore --hidden`, `dt-keys list` |
| **Thread-state deletion in the DB reaches messages and quant runs** | **CONFIRMED** | `conversations-repo.ts:194` owner-scoped delete; `schema.ts:96`/`:75` cascade; `drizzle/0001`+`0002` applied SQL |
| **A browser-localStorage copy of full message text survives deletion** | **CONFIRMED** | `thread-local.ts:54` `saveLocalThreads()`; `chat-shell.tsx:278` only fires server DELETE for remote threads |
| **Embedding/vector deletion is possible** | **CONFIRMED THAT IT IS NOT** | `digisearch/server.py:1674` raises HTTP 501 "not implemented for this digisearch deployment"; `azure_search.py` has no `delete` |
| **Tarball backup retention exists** | **CONFIRMED** | `dt-backup` `cmd_prune()` line 261 local; 273–304 remote via `rclone delete --min-age` |
| **`dt-snapshot` refs are pruned** | **CONFIRMED THAT THEY ARE NOT** | No `prune`, `gc`, `expire`, `ttl` or `update-ref -d` anywhere in `dt-snapshot`. 83 local refs, **74 on a public remote** |
| **Snapshot trees currently contain no client data** | **CONFIRMED, verified not assumed** | All 83 local `refs/backup/**` refs checked; only `projects/README.md` under `projects/` |
| **The public snapshot remote is public** | **CONFIRMED** | `gh repo view digithings-ai/digithings` → `{"visibility":"PUBLIC"}`; `pushBackupsFor` matches it |
| **Audit JSONL is unbounded** | **CONFIRMED** | `digibase.audit.emit_event` appends to `AUDIT_LOG_PATH`; no retention or rotation code exists |
| **`projects/*` is unreadable to a non-engagement agent** | **CONFIRMED THAT IT IS NOT** | One shared unix user; `projects/` is `drwxr-xr-x`. `.gitignore:41` prevents commits, not reads |
| **Credential scanning covers `projects/*/vault/`** | **CONFIRMED THAT IT DOES NOT** | `.gitleaks.toml:39–42` allowlists `^projects/[^/]+/vault/` |
| **Two secret redactors exist and neither is Art. 9** | **CONFIRMED** | `digitrace/redaction.py` (3 regexes, LangSmith egress only, inert without `LANGSMITH_API_KEY`); `digibase/audit.py` (key-name based) |
| Whether an Art. 46 mechanism exists today | **UNKNOWN** | Not found in the repo; may exist in client paperwork. Chris has ordered the work |
| Whether a candidate provider will sign Art. 46 safeguards | **UNKNOWN** | Not yet asked |
| Retention periods | **DECIDED, not yet enforceable** | Chris `d90_30_split`; §6 shows two stores with no retention today |

**Sourcing limitation, recorded for honesty.** EUR-Lex was unreachable from this session (HTTP 202 bot challenge on
every attempt, 2026-10-05). The article text above was read from a reproduction of the Regulation, and
cross-checked against the UK consolidated text on legislation.gov.uk. **Both are copies, not the Official Journal.**
Chapter V (transfers, Art. 44–49) is the area where national derogations and amendments matter most, so the
transfer reasoning in §0.2 and §10 should be confirmed against the current consolidated EU text before it is
relied on externally. I have not asserted CONFIRMED on anything I read in only one copy.

**A second sourcing limitation, about Security's half.** Every technical finding in §2, §5, §6 and §7 rests on
Security's DIG-567 run `3ef5184a` against the monorepo at commit `9bee32091`. **I have read those answers; I have
not independently re-run those commands.** They are strong — file-and-line evidence, negative searches stated
with their scope — but they are one agent's reading of one commit. If a finding here is load-bearing for a client
commitment, re-verify it before relying on it.

---

**Advice only. Counsel signs and sends nothing. Twelve-x stays anonymous. Chris has decided the open questions in
§11; two are accepted knowingly rather than fixed, and four controls in this page are now known to be weaker than
revision 1 claimed. This page is not a compliance record.**