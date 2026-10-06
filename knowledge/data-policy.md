# digithings client data and data protection policy

One page. What we keep, how long, which models may see it, what is anonymised, how deletion works, who may touch it.
Written by Counsel with Security, 2026-10-05. Decision owner: Chris.

**Revision 5, 2026-10-05 — the 7th published revision of this document.** Revision 1 was Counsel's opinion about
four controls nobody had verified. Revision 2 folded in Security's answers verbatim. Revision 3 read the same model
provider as a **contract counterparty** and surfaced two findings no decision covered. **Revision 4 does one thing:
it records Chris's answers to both of them, and then carries the consequence.**

1. It records **Chris's answers to card `55b459c0`**, answered 2026-10-05T11:17:59Z — **`accept_warranty_risk`**
   (the rights warranty, CR2) and **`accept_second_risk`** (the second processing purpose, CR6). Both are §10.2.
2. **CR2 and CR6 move from "open" to "accepted, and recorded".** No finding on this page is now undecided. §11's
   "Still open" list loses both and keeps only the four questions that were never put to him.
3. **It says plainly what acceptance did not do.** Counsel's recommended fix for CR2 was a client warranty (§10.3
   clause 3) and for CR6 the same clause reached from the other side. **Chris chose acceptance instead, so those
   drafts are marked not-adopted and are not offered to any client.** The drafts stay in the file because they are
   the cheapest fix if either decision is ever revisited — not because they are in use.

**Nothing in §2, §5, §6 or §7 changed.** Security's answers stand exactly as revision 2 left them: where Security
wrote **not implemented**, this page says not implemented, and where Security wrote **cannot tell**, it keeps
UNKNOWN. None of those gaps have been softened. **Nothing in §1, §3 or §4 changed either** — no retention period, no
model rule and no processing purpose moved in this revision. This revision only decides who owns two risks.

**Revision 5 does one thing: the DPIA question in §8.3 is answered.** Counsel did the assessment rather than
leaving it at LIKELY, published it as `knowledge/dpia.md` on DIG-893, and rewrote §8.3 to match. **The answer is
that a DPIA is owed — CONFIRMED**, on 7 of 9 WP248 criteria and on Garante provv. 467/2018 item 7. **Nothing in
§1–§7 or §9–§10 changed.** No retention period, no model rule, no processing purpose and no decision of Chris's
moved. **What did change is the gate: it is Article 9, not Article 35.** A DPIA cannot create an Art. 9(2)
exception, so "do a DPIA" was never the real blocker on the next client dataset. §8.3 has the detail.

**8.3 gate statement as Chris decided it, 2026-10-05T17:31:05Z — `wait`.** Card `eaaf3ab1` on DIG-921
(`human_only`). **The next client dataset does not land until the measures in the assessment are built.**
Counsel's recommendation was `wait` and Chris took it, so the gate is now a decision and not only Counsel's
assessment. **The basis is unchanged and was not decided by Chris:** the Art. 9(1) prohibition is
**CONFIRMED**, no Art. 9(2) exception is identified (**LIKELY**), whether one covers what we actually do is
**UNKNOWN** (`knowledge/dpia.md` §7), and a DPIA **cannot create an exception**. The measure that ends the wait
is **DIG-912** (CTO, the Art. 9 filter). **`wait` is the only answer that leaves that basis intact** — "start"
would have run against the assessment without changing a word of it.

**Revision 6, 2026-10-05 — it records Chris's answers to the three client-data questions.** Card **`eaaf3ab1`** on
DIG-921, `human_only`, **answered 2026-10-05T17:31:05Z** by Chris (`resolvedByUserId: local-board`). These are
**Chris's answers, not Counsel's recommendations.** On q3 he took the opposite of the pick Counsel recorded.

| # | Question | Counsel's recommendation | **Chris's answer, 2026-10-05T17:31:05Z** |
|---|---|---|---|
| q1 | May the next client dataset land before the 14 measures are built? | `wait` | **`wait`** — he took Counsel's recommendation |
| q2 | Do we stop pushing snapshot refs to the public remote? | `stop` | **`stop`** — he took Counsel's recommendation |
| q3 | Prepare an external DPO, or accept the exposure? | `accept`, with a re-open trigger | **`prepare`** — **he declined Counsel's recommendation and chose to spend money** |

**What each answer does, in one line each.** q1 makes §8.3's gate a **decision** instead of Counsel's own
assessment. q2 stops future pushes but **does not un-publish the 74 refs already on the public remote** — that
exposure is permanent and is now recorded as such. q3 authorises preparing an external DPO, which **costs money
and engages new duties**, and which **does not resolve the Art. 37(1)(c) question** — that label stays **UNSURE**.

**No sentence in §1–§7, §9 or §10 changed.** No retention period, no model rule, no processing purpose, no
contract finding and no other decision of Chris's moved in this revision.

**Four citation errors were found and corrected while recording q3, and all four were Counsel's.** Chris's
`prepare` answer made Arts. 37–38 load-bearing, so Counsel re-read them against the Official Journal text
(CELEX 32016R0679). **Art. 37(1)(b) is wrong on this page and was wrong in every earlier revision: (b) is
large-scale regular and systematic monitoring. The Article 9 trigger is Art. 37(1)(c)** — "the core activities of
the controller or the processor consist of processing **on a large scale** of special categories of data pursuant
to Article 9 and personal data relating to criminal convictions and offences referred to in Article 10".
**Art. 38(3) is not the external-DPO clause: it is the independence guarantee** (no instructions, no dismissal,
direct report to the highest management level). **The external officer is made lawful by Art. 37(6)**: "The data
protection officer may be a staff member of the controller or processor, **or fulfil the tasks on the basis of a
service contract**." **And optional designation, where 37(1) does not apply, is Art. 37(4), not Art. 37(3)** — 37(3)
only lets a single officer cover several public authorities.

> **Correction of a correction, 2026-10-05, second pass.** Revision 6 recorded the external-DPO clause as
> **Art. 37(5)** and optional designation as **Art. 37(3)**. Both were still wrong, and were introduced by the very
> note that fixed 37(1)(b) and 38(3). The substance is unchanged — 37(5) is the professional-qualities duty
> ("designated on the basis of professional qualities and, in particular, expert knowledge of data protection law
> and practices") and 37(3) is the public-authority rule, neither of which is the clause relied on here. **This is
> why the correction note above had to be re-verified against the source rather than against the previous
> revision.** Anyone quoting this page should quote 37(6) for the service-contract route and 37(4) for optional
> designation.

**The conclusion did not change at any point — the duty is still UNSURE and the external route is still
available — but the citations were wrong and are now right.** **Why it matters anyway:** the conclusion survives a wrong citation by
luck, not by reasoning. Anyone who checked (b) against the text would have found the analysis unsupported, and
Chris is spending money against it. `knowledge/dpia.md` §5 carries the same two errors and is corrected there too.

**Revision 7, 2026-10-06 — it records the CTO's decision on DIG-785, and corrects two §7 claims that were wrong.**
Three things change, all inside §7. **No retention period, model rule, processing purpose, contract finding or
decision of Chris's moved**, and nothing in §1–§6 or §8–§11 changed.

1. **The CTO decided `accept_and_document`** on the `projects/*` access boundary: the boundary stays a convention,
   and the technical control becomes a scoped, owned, dated piece of hardening rather than a prerequisite. §7 now
   carries the residual risk with a named owner (Platform) and states plainly that nothing here is enforced.
2. **The git-history claim in §7 was wrong and is corrected.** The three Twelve X commits are **reachable from
   tags, not branches**, so `git gc` will not prune them. See the correction block in §7.
3. **The credential-scanner finding in §7 is now fixed** and the finding is restated as historical. The path
   exemption is gone and gitleaks scans new `projects/*/vault/` files normally.

**Status: ADVICE with Security's verified findings folded in. This page is not a compliance record and it does
not by itself satisfy any GDPR obligation.** The DPIA in `knowledge/dpia.md` is the assessment Art. 35 requires; it
is a draft for Chris and Counsel has not signed or filed it.

**What changed from revision 1, in one line: it reads worse, because it is truer.** Revision 1 asserted four
controls; Security found **one does not exist**, **one is the wrong kind of control**, and of the three UNKNOWNs,
**one is known-broken**. Two claims in revision 1 were simply wrong and are corrected below. Nothing was
improved, softened or substituted.

Clients are referred to by codename. **twelve-x stays anonymous in every artefact, including this one.** Exactly
one other client's name appears anywhere on this page, in §7, and only because the name is already public: it is
a git repository name on a public remote. That is evidence, not a disclosure.

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

**0.5 — Two contract findings are now accepted rather than open, and one of them is not a transfer at all.** Chris
answered both on 2026-10-05. **CR2** is a rights warranty we may already be giving the provider and cannot honour.
**CR6** is a second processing purpose created by the provider's own Terms because our model account is unpaid.
**Neither is fixed; both are owned.** Read them in §10.1 with the other four findings, in §10.2 as decisions, and
notice this: **CR6 is not a Chapter V transfer problem and no amount of Art. 46 work touches it.** It is a
purpose-limitation and lawful-basis problem, and it is now the one finding on this page that is accepted, recorded,
and still not disclosed in any notice we owe.

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
and **Chris decided on 2026-10-05 that they stop being pushed — `stop`, card `eaaf3ab1`, 17:31:05Z**, taking
Counsel's recommendation. **That decision is forward-looking only, and the distinction is the whole point.**
Deleting or un-pushing the remote does not un-publish what is already there, so **the 74 refs remain clonable
and must be treated as permanently exposed.** The question Chris answered was *may we keep publishing*, and
the answer is no. The question nobody has answered is *what we do about the copies already out*, and that is a
separate decision this page does not make.
under `refs/backup/**` — not on `refs/heads`, so invisible to ordinary browsing. They hold no client data now,
but they are a standing egress channel for everything tracked, **and secret history has already passed through
them**: existing backup refs are named for DIG-179 ("live-proton-mailbox-password-is-committed-in-plain-text")
and DIG-41 ("apply-credential-scrub"). Security filed **DIG-784** for this.

**Owner and state, added 2026-10-05 so the next reader does not restart this.** The engineering question is
**DIG-784** (Security, `in_progress`, high), whose own work item 2 is "Settle whether snapshot refs belong on a
public remote at all. Recommend: not" — Security had already written the recommendation down, with the verified
`{"visibility":"PUBLIC"}` and 74-ref evidence inside it. **Chris answered that question on 2026-10-05: `stop`
(card `eaaf3ab1`, 17:31:05Z).** Two things follow, and the second is the one that matters. **First, the fix has
an owner and the decision now backs it — DIG-784 stops future pushes.** **Second, the exposure in this subsection
is a measured fact about today, and the decision did not touch it** — the 74 refs are clonable by anyone right
now, and stopping the push does not un-publish them. **The one thing that would change that is scrubbing the
already-pushed refs off `refs/backup/**` on the remote, and no one owns that decision.** Counsel's reading:
it is worth asking, because secret history has already passed through these refs, and it is a question for
Security and Chris, not for this page.

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

### What `.gitignore` never enforced

**Every agent in this company runs as the same unix user, `chrisstefan`.** `/Users/chrisstefan/Code/digithings/projects`
is `drwxr-xr-x` — world-readable — and holds `README.md`, `local/`, `sitaas/`, `twelve_x/`,
`twelve_x.egg-info/` and `v-simple.md`. Security's direct answer to the question this page should have asked:

> Yes — a non-engagement engineer can read all `projects/*` client data today, on any issue, with no tool or
> permission required.

Until the guard shipped, the only thing in the way was a sentence in the root `AGENTS.md` — "`projects/` is
confidential — never push to public remotes." **That was a convention, not a control.** A convention is worth
having; it is not Art. 32(1)(b) "the ability to ensure the ongoing confidentiality", because nobody demonstrated
the ability.

**This has changed as of the DIG-1302 control below.** The refusal of out-of-scope reads is now performed by the
agent runtime, not asserted here. **`.gitignore` is unchanged by it: `.gitignore` prevents a commit and has never
prevented a read.** Do not cite it as the access control, and do not treat the guard as making `projects/*`
commit-safe — the two are independent.

### The control, once the CTO chose it

**LANDED on DIG-1302, 2026-10-06 — the third of the three options above, built as specified.** The enforcement
point is the agent runtime's tool-call boundary, in the opencode plugin
`.opencode/plugins/projects-path-guard.js`:

- **Default-deny under `projects/`.** Exactly two allowances: `projects/README.md` (tracked in git, not client
  data) and `projects/<engagement-dir>/**` for the single engagement bound to the run.
- **The engagement directory is read from an explicit mapping**, `config/engagement-paths.json`, never derived
  from the engagement name. `twelve-x` → `twelve_x` is written down as data. An engagement with no entry in the
  mapping resolves to **no allowlist at all**.
- **Fails closed.** No bound engagement, a missing or unreadable mapping, or a path the guard cannot evaluate are
  all denials. There is no path through which an unevaluable input becomes an allow.
- **Normalised before matching.** `..`, absolute paths and symlinks are resolved to a real path first, so
  `projects/A/../../B/`, an absolute path into another engagement, and a symlink under the bound engagement that
  points elsewhere are all refused.
- **Covers every read path**, not one tool: file read and edit, `grep`, `glob`, `list`, and the path arguments of
  shell execution. A `grep` with no path argument from the repository root is refused too, because the repo root
  contains `projects/`.
- **Every denial is logged** as a `projects_path_denied` audit event, carrying the tool, the reason, the bound
  engagement and the refused paths. Silence stays distinguishable from a guard that is not running.
- **One engagement per run**, not per agent or per day: a run holds the engagement named in `DIGI_ENGAGEMENT`,
  so a single run cannot hold two engagements' paths.
- **Kill switch:** `DIGI_PROJECTS_PATH_GUARD=off` disables enforcement and is itself logged. Any other value,
  including an unrecognised one, enforces — a control that silently fails open on a typo is not a control.

**Tests:** `tests/scripts/test_projects_path_guard.py` (29 tests, in `pytest -m unit`), driving the shipped
JavaScript rather than a re-implementation, with real directories and a real cross-engagement symlink. They were
mutation-checked: replacing the allowlist with allow-everything fails 16 of them, and removing symlink resolution
fails the two symlink tests.

**Known limit, stated so nothing overclaims.** The guard decides on paths. It does not inspect file contents, and
it cannot constrain what an already-authorised read is later used for. It also does not constrain code that reads
`projects/` by a route other than an opencode tool call — an MCP server or a script run outside this runtime is
outside its reach. It is a boundary against **an agent going off-task through its own tools**, which is the
threat the CTO named when choosing it, and it is not a general data-loss-prevention control.

### Client data is already in git history

**`.gitignore` cannot un-track anything.** Commits `6e9cd9cc9` and `1dbd3db74` still carry `projects/README.md`
and **are reachable from 1,599 and 1,582 branches respectively**, so they are in any clone.

Commits `1a657079c`, `18cd7c997` and `b8c1b76d8` (the Twelve X FX research project, including
`projects/twelve_x/vault/**`) carry real client research. **They are reachable — but only from tags, not from any
branch**, which is why `git branch --contains` reports them as unreachable. Security re-verified this on 2026-10-06
with `git for-each-ref --contains`: `1a657079c` is contained in `refs/tags/stash-archive/28` and `/29`,
`18cd7c997` in `/29`, and `b8c1b76d8` in `/28`. There are 45 local `stash-archive/NN` tags (2026-04-19 to
2026-08-10). **`git gc` will not prune them while those tags exist.** They are on **no remote** — `git ls-remote
--tags` finds zero `stash-archive` tags on either `github` or `origin`.

> **Correction, 2026-10-06.** Revision 5 said these three commits were "unreachable … and therefore dangling —
> but the object blobs still exist locally and stay recoverable until `git gc` prunes them". That was wrong in the
> operative part: `git gc` **cannot** prune them, because the `stash-archive` tags hold them reachable. Counsel must
> publish neither "a local `git gc` will clear it" nor "client data is on a public remote". **Client data is in
> reachable local repository history, and on no remote.**

### The credential scanner was muted on that same path — that is fixed

Revision 5 recorded: `.gitleaks.toml:39–42` allowlisted `'''^projects/[^/]+/vault/'''`, commented "confidential
research vaults … never pushed to public remotes". The effect was that **gitleaks would not report a credential
committed inside any `projects/*/vault/` file**, forever, and the stated reason was a confidentiality claim that a
credential scanner cannot act on.

**Fixed on DIG-785, 2026-10-06.** The path exemption is deleted and the replacement is scoped to the single commit
that actually carries findings. Measured, on the removed exemption's own justification:

- The findings it was hiding are **not prose**. All six are genuine 20-character AWS-access-key-ID-shaped strings —
  `secretLen` 20, entropy 3.52, key-ID prefix test true — inside third-party broker research briefs in
  `projects/twelve_x/vault/briefs/2026-06-05/`. **The "research prose that occasionally matches" comment was not
  true.**
- On remote-visible history the mute **was hiding nothing**: `gitleaks --branches` returns 5 findings before and
  after the change and **0 of them under `projects/`**.
- **No rotation is owed.** `docs/ops/SECRETS_INVENTORY.md` lists **zero AWS credentials**, so these six cannot be
  ours and there is nothing at any provider to rotate.

**New vault files are now scanned normally.** `.gitignore` still does not reduce gitleaks' scan surface — `gitleaks
dir .` reports credentials inside ignored directories — so gitleaks was never an access boundary, and it is still
not one. This fix removes a false negative; it adds no control over who may read `projects/*`.

### The decision, and the residual risk that is being carried

**DECIDED, 2026-10-06 — CTO, on DIG-785: accept and document, with the named compensating control.** At the moment
of the decision the `projects/*` boundary was a **convention**; the control the CTO chose in place of per-engagement
unix accounts has since been built and merged (DIG-1302, 2026-10-06). This section is the record of the decision,
the reasoning and what was still open alongside it. `.gitignore` remains commit-prevention only throughout.

The CTO's reasoning, recorded because the reasoning is what Counsel may rely on: per-engagement unix accounts and
OS ACLs cost real operational drag against three engagements, one operator and one shared unix user, and buy
little in return. The threat that matters is **an agent going off-task**, and that is cheap to address.

**The residual risk as it stood when the decision was taken.** The first bullet is closed by the control; the other
two are not, and the guard does not reach either.

- **A non-engagement engineer or an off-task agent can read all `projects/*` client data today**, with no tool, no
  permission and no audit trail. There is one unix user. The only barrier is a sentence in `AGENTS.md`.
- **Client data sits in reachable local git history** via the 45 `stash-archive/*` tags described above, and is on
  no remote. Tags are local-only, so this is a workstation-retention and backup-scope question, not a disclosure.
- **Owner of the compensating control: Platform**, per the CTO. The control is a **path guard in the agent
  runtime** that refuses reads under `projects/*` outside the current engagement's allowlist. **Security specifies
  the allowlist rule**; Platform builds it. **Due within the current quarter.** Tracked as a child of DIG-785.
  **Built on DIG-1302 and merged — see "The control, once the CTO chose it" above.** The bullets under
  "The residual risk, named" describe the position before that control and are kept as the record of what the
  risk was; read them as history, not as the current state. What remains open after the guard: nothing in the
  guard's own scope, and the two items below that it does not touch.
- **Security's own remaining item:** expire the `stash-archive/*` tags so those three commits stop being reachable,
  coordinated with DevOps.

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

## 8. Three obligations we did not meet

These are not policy gaps. They were missing artefacts. **Two are still missing (8.1, 8.2). The third now exists
as a draft (8.3).**

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

**The one purpose this notice cannot yet truthfully state, and why accepting it did not fix that.** Chris has accepted
the second processing purpose created by the provider's unpaid-account clause (`accept_second_risk`, §10.2). **An
accepted risk is still a purpose.** This notice must state purposes, and if the provider in fact uses our content to
improve its service then that is a purpose we are disclosing nothing about. We cannot write the sentence honestly
either way: we cannot say it does not happen, because the Terms permit it and we have no way to observe it, and we
cannot say that it does, because we do not know. **The two ways out are to stop the purpose or to find out whether it
is happening — and neither is a drafting task.** Recorded here so the notice, when it is written, does not quietly
omit a purpose.

**8.3 — A DPIA is required, and it now exists.** **This finding moved off LIKELY on 2026-10-05.** The previous
revision said the question needed "a real risk assessment, not my reading of one clause". That assessment has now
been done and is published as `knowledge/dpia.md` (issue DIG-893). **Chris then decided the gate itself on
2026-10-05: `wait`, card `eaaf3ab1` on DIG-921, 17:31:05Z.** The finding below is unchanged; the wait is now his
decision on top of it.

> **Finding: a DPIA is required before digithings processes the next client dataset. CONFIRMED.**

**Basis, stated so it can be checked.** Art. 35(1) requires an impact assessment *before* processing where it "is
likely to result in a high risk". Scored against WP248 rev.01's nine criteria, the processing meets **seven of nine**,
against a two-criterion threshold. Two independent pillars, either sufficient on its own:

- **Art. 35(1) with WP248:** "the occurrence of two or more of these criteria is indicative of processing that
  presents a high risk and for which a DPIA is required (WP 248, rev. 01, p. 11)". Met: evaluation/scoring (1),
  systematic monitoring (3), sensitive or highly personal data (4), large scale (5, LIKELY), matching or combining
  datasets (6), vulnerable data subjects (7, LIKELY), innovative technology (8).
- **Garante Provv. 467/2018, Allegato 1, item 7:** processing through innovative technologies — the list names AI
  systems — requires a DPIA "**ogniqualvolta ricorra anche almeno un altro dei criteri individuati nel WP 248,
  rev. 01**". That matches us on its face. Items 4 and 10 also match.

**Art. 35(10) does not exempt us** — it applies only to Art. 6(1)(c)/(e) processing already covered by a general
impact assessment under law, and we are controller on our own purposes. **No Art. 35(5) exclusion exists**: the
Garante has drawn no no-DPIA list ("Allo stato, non è stato redatto e/o comunicato alcun elenco del genere").
**The Digital Omnibus does not help** — it is a proposal, not law (COM(2025) 837, procedure 15698/25, still in
negotiations as at 2026-10-05), and the Presidency compromise recital 40 **keeps Art. 35(1)'s "high risk" trigger
intact**. Anyone who says the Omnibus raises the DPIA threshold to "very high risk" is wrong.

**Security's findings made this worse, and they are now scored, not listed.** The assessment scores **14 risks** on
likelihood × severity. **Seven are "very high" inherent.** The four that drive the result: Art. 9 content arrives
unfiltered (§2, R1, 16); `projects/*` access is unenforced (§7, R2, 16); two stores are unbounded and 74 snapshot
refs sit on a **public** remote (§6, R3, 12); and no pseudonymisation exists at all (§5, R9, 12). **Erasure also
cannot reach the vector index (R4) or the browser (R5).**

**What the assessment changed about the answer.** Three things, and the third is the operative one:

1. **Prior consultation with the Garante (Art. 36) is NOT yet owed. LIKELY.** Art. 36(1) triggers where risk is
   high "**in the absence of measures taken by the controller to mitigate the risk**" — and we have not taken
   them. Firing a consultation today would be premature on the law and would disclose the Art. 9 and transfer
   positions to the Garante before either is fixed. Consultation becomes owed only if residual risk is still high
   **after** the measures are built.
2. **A DPO question falls out of the same facts. UNSURE.** No DPO is designated, which does not itself breach
   Art. 35(2). But if "large scale" Art. 9 processing is conceded, **Art. 37(1)(c) arguably obliges one** — and
   Art. 37(6) allows an external DPO, the realistic route for a sole freelancer. This is the strongest reason to be
   careful with the word "large scale".
3. **The gate on the next dataset is Article 9, not Article 35.** A DPIA documents and mitigates risk; it **cannot
   create an Art. 9(2) exception**. If we read clients' correspondence containing Art. 9 content with no exception,
   the problem is not that we have not assessed it — the problem is that we may not do it at all. **Until an
   exception is identified or an Art. 9 filter exists, the next client dataset should not land.** That is a
   stronger and simpler statement than "do a DPIA", and it is the one to act on.

The assessment is a **draft for Chris**. Counsel does not sign, file or send it.

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

### 10.1 The same provider as a contract counterparty

Added 2026-10-05 from [DIG-658](/DIG/issues/DIG-658). Read in full from
`https://opencode.ai/legal/terms-of-service` — effective date **Aug 15, 2026**; counterparty **ANOMALY INNOVATIONS,
INC.**; contact `help@anoma.ly`. `/terms`, `/terms-of-use`, `/legal/terms`, `/legal` and `/privacy` all return 404,
so the live path is the long one. Recorded so the next reviewer does not conclude the document is gone.

Everything above this subsection is regulatory. **This part is contract**, and it belongs here because both halves
are triggered by the same fact: every client-data agent runs on this provider's free, unnamed model. A contract is
not a regulator, does not fine us, and cannot be discharged by writing a risk down.

| # | Finding | Label | What it actually costs |
|---|---|---|---|
| **CR1** | **Third-party-use clause.** "You will only use the Services for your own internal use, and not on behalf of or for the benefit of any third party, and only in a manner that complies with all laws that apply to you." | **Coin-flip on the text.** The no-breach reading is **LIKELY** better, **not CONFIRMED** | A Delaware-governed breach. **Chris accepted it knowingly on 2026-10-05 (§10.2)** |
| **CR2** | **Rights warranty.** "You represent and warrant that you have all rights, licenses, and permissions needed to provide Input to our Services." | CONFIRMED as Terms text. **Breach status UNSURE** — we may already be warranting something false | **ACCEPTED as a known risk on 2026-10-05 (`accept_warranty_risk`, §10.2). Not fixed, and the warranty is not withdrawn by accepting it** |
| **CR3** | **Suspension right.** "OpenCode is also free to terminate (or suspend access to) your use of the Services for any reason in our discretion, including your breach of these Terms." No cap, no notice, no cure period | CONFIRMED as Terms text | **This is the real exposure, not the $100 cap** — losing the model layer mid-engagement |
| **CR4** | **Uncapped indemnity.** "You agree to indemnify and hold the OpenCode Parties harmless from and against any and all claims, liabilities, damages (actual and consequential), losses and expenses (including attorneys' fees) arising from or in any way related to any claims relating to (a) your use of the Services, and (b) your violation of these Terms." | CONFIRMED as text. Whether the liability cap reaches an indemnity **we owe** is **UNSURE — flagged, not asserted** | Unbounded on its face |
| **CR5** | **Personal counterparty.** "Your use of the Services in any way means that you agree to all of these Terms"; and where the Terms say "if you are not agreeing to the Terms on behalf of an organization or entity … the references to 'you' and 'your' in these Terms, except for in this sentence, refer to that organization or entity". **No digithings Zen account exists.** | CONFIRMED as Terms text. **UNSURE which person is bound** — no individual acceptance record has been located | Delaware forum, JAMS streamlined rules, jury waived, assignment barred without the provider's written consent, and the provider pays its own arbitration fees on claims under $75,000 |
| **CR6** | **A second processing purpose, on an unpaid account.** See below — the trigger is **CONFIRMED** | Trigger **CONFIRMED** by direct experiment. Whether the right is **exercised** is **UNKNOWN and unverifiable** | **ACCEPTED as a second known risk on 2026-10-05 (`accept_second_risk`, §10.2). Not fixed, not disclosed, and not cured by any Art. 46 work** |

**CR1 — why it is a coin-flip, and what actually decided it.** *Reading A, breach:* the clause is disjunctive, and
"**or for the benefit of any third party**" does not say resale. Every client deliverable is produced for a client's
benefit, so on the literal wording the clause is hit every time. *Reading B, no breach:* the clause sits among resale
and white-labelling restrictions; "on behalf of" is agency language, and we are an independent contractor rather than
the client's agent; and the Terms elsewhere assign Output to us with no restriction on downstream use ("you (a)
retain your ownership rights in Input and (b) own the Output"), which is incoherent if commercial use of the output
were forbidden. **Assessment: the no-breach reading is LIKELY to be the better one — LIKELY, not CONFIRMED, because
the deciding words are "or for the benefit of any third party" and an arbitrator can read them literally.**

**The action that is clean on either reading, and what Chris chose instead.** Keep third-party content out of the
model layer entirely. If no third-party Content is in the session, no third-party benefit is derived from the
Services, and CR1 does not bite — on either reading. That is the same action §10's Art. 46 gap wants, reached from a
**contractual** direction instead of a regulatory one, which is what made it the one recommendation that addressed
both at once. **Chris chose the other branch and accepted the breach knowingly (§10.2).** Counsel's note for whoever
reads this next: the recommendation is not withdrawn, it is deferred — and it is still the cheapest fix available. It
costs no money, needs no provider's cooperation and no client conversation, and it is the only option that also
removes CR1 as a trigger for CR3.

**CR2 comes before the transfer question in sequence, and Chris has now decided it by acceptance rather than by
drafting.** The warranty is about the **inputs** we hand over, not the country they land in. For a client email
archive or a chat export full of named third parties we almost certainly do not hold "all rights, licenses, and
permissions needed", and **no client contract carries a transfer clause yet**, so there is nothing to point at.
Whether "permissions needed" reaches processor sub-processing is a question the Terms do not answer — hence UNSURE
on breach status, and that label has **not** moved. **What Chris answered** is `accept_warranty_risk` — accept the
warranty exposure and record it as a known risk (§10.2). **Counsel's route was the other one:** a matching warranty
in the client contract (§10.3, clause 3), which is cheap and is the only fix that closes CR2 and CR1 together,
because a client that warrants its own rights is also a client whose data we are entitled to pass onward.

**Three things acceptance did not do, stated so nobody later reads the decision backwards.** It did not make the
warranty true — the sentence in the provider's Terms is unchanged and we are still giving it every time we send an
input. It did not withdraw the warranty, because a provider's Terms admit no withdrawal by the customer. And it did
not move breach status off UNSURE: **we still do not know whether we are already in breach**, and acceptance is a
decision about what to do about that uncertainty, not an answer to it. Counsel's clause 3 is marked **not adopted**
in §10.3 for that reason, and it stays there as the cheapest way back if this is ever revisited.

**CR5 is what turns CR1 from a fine into a business risk.** New Castle County, Delaware; JAMS streamlined rules;
good-faith negotiation as a precondition to arbitration; jury trial waived; assignment barred without the provider's
written consent. And since the provider "will pay all arbitration fees for claims less than seventy-five thousand
($75,000) dollars", the remedy is cheap for them and expensive for us in time. **This is personal exposure, not
corporate** — an Italian resident litigating in Delaware over work done for a client. That is why the third-party-use
clause mattered more than its $100 cap ever suggested. Chris has accepted it and recorded it (§10.2).

**CR6 — the unpaid account, and the purpose no notice discloses.** The trigger was settled by **experiment**, not by
reading a billing page (2026-10-05, [DIG-658](/DIG/issues/DIG-658)):

- `POST /zen/v1/chat/completions` on `opencode/space-bunny-free` — the model all ten client-data agents run on —
  returns **HTTP 200 with `"cost":"0"` and no `Authorization` header at all**.
- Every paid model returns **HTTP 401** without a valid key, and **HTTP 402 "Insufficient account funds"** on the
  only key on this machine.
- No credential is injected by the harness, and none is registered in the agent's credential store.

**CONFIRMED: we are on the unauthenticated free tier, so the clause's trigger is textually live on our access
path.** What remains UNKNOWN is only whether the provider in fact exercises the right. The clause, verbatim:

> "We use Content to provide our Services, comply with applicable law, enforce our terms and
> policies, and keep our Services safe. In addition, if you are using the Services through an unpaid
> account, we may use Content to further develop and improve our Services."

Counter-evidence, recorded because it is real and because it does not close the risk. The provider's `/docs/zen`
page carries a Privacy block, and the model in question is **not** in its exception list:

`/docs/zen` page carries a Privacy block: "All our models are hosted in the US. Our providers follow
a zero-retention policy and do not use your data for model training, **with the following
exceptions:**" — and the exception list enumerates nine models (Big Pickle, Fledge Alpha Free,
MiMo-V2.6-Flash Free, MiMo-V2.5 Free, Ling 3.1 Flash Free, Ling 3.0 Flash Fin Free, Nemotron 3
Ultra Free (NVIDIA), Nemotron 3.5 Lightning Free (NVIDIA), Muse Spark 1.3 Contributor Free).

`space-bunny-free` is absent from those nine; its own entry says its provider "follows a zero-retention policy and
does not use your data for model training". Three reasons that does not settle it, all recorded as UNKNOWN or UNSURE
rather than smoothed over:

1. It is a **documentation page, not the binding Terms** — the same defect §0.2 already records for the US-hosting
   statement. A carve-out on a non-binding page does not narrow a binding clause.
2. `space-bunny-free` is described by the provider as "a stealth model that's free on OpenCode for a limited time",
   so the processor is unnamed and its own terms can never be read by us.
3. Whether the improvement right is **exercised** is not observable from outside the provider. There is no account,
   plan or usage endpoint to check — every one probed returned 404.

**Why CR6 is a different problem from everything above it.** If the improvement right is exercised, that is a
**further processing purpose** — not a transfer, and not a storage question. §1's lawful-basis table has no row for
it, and §8.2's notice cannot truthfully disclose it. That makes it a purpose-limitation and lawful-basis problem on
top of the transfer exposure, cited as Art. 5(1)(b) and Art. 6 **by article number only**, with the text **not**
re-verified this run — treat the numbering as **UNSURE**. The conclusion does not depend on the numbering: a second
purpose that no notice discloses is a problem whatever the articles are called.

**Chris has now answered it — `accept_second_risk` — and the answer was to accept, not to close.** `accept_exposure`
had accepted the transfer, and `accept_breach` had accepted CR1; **neither of those touched a second purpose with no
lawful basis behind it**, and this answer does. Recorded as a **second known risk, separate from the transfer
exposure**, so the register does not let it hide inside a decision that was about something else. **The three
consequences that survive it, unchanged:** Art. 6 still needs a lawful basis for the improvement purpose and we
have not identified one; §8.2's notice still cannot truthfully disclose a purpose we have not confirmed is
happening; and the Art. 30 record still has to state purposes, not record acceptance in place of them. Counsel's
note on the one option that closed CR6, CR1 and §10's Art. 46 gap at the same time — the §10.3 clause 3
client-warranty route — is **not withdrawn, it is declined for now**; Chris took the acceptance branch instead.

### 10.2 What Chris decided about the contract, and what acceptance does not do

**Two cards, four answers, all on 2026-10-05.** Card `03401674` was answered at 10:18:57Z and card `55b459c0` at
11:17:59Z. All four answers are recorded below as his decisions, in the order they came. Counsel's advice sits next
to each of them, not in place of them. **Between them, every finding in the §10.1 register now has an owner.**

| Question | His answer | What it settles | What it does **not** settle |
|---|---|---|---|
| **Does running client work through the model breach the third-party-use clause?** | **`accept_breach`** — "Knowingly accept the contract breach" | CR1 becomes an owned, accepted contract risk instead of an open question. Counsel had recommended the clean-by-conduct option instead (§10.1) | It does not make CR1 **permitted** — nothing in the provider's Terms permits it. And it does not touch CR3: accepting the breach **strengthens** the provider's contractual ground to suspend us under CR3 |
| **Who do the provider's Terms bind — the business, or Chris?** | **`accept_personal`** — "Accept it and record it as a known risk" | CR5 is recorded as a known risk with a named owner, on Chris, knowingly | It does not move the counterparty. The bound person is still whoever uses the service, and there is still no digithings account |

**The Italian forfettario question is now settled, and the answer is "no change".** Counsel said it would not move
on whether restructuring through the business entity might touch the forfettario position without Chris's explicit
approval. **`accept_personal` is that answer**: we are **not** restructuring the contract through the business, so
the tax position is untouched by this decision. Recorded here so the next reviewer does not re-open it as a pending
item. This is not tax advice, and nothing about the forfettario calculation, rate, coefficient or deadline has been
examined or changed.

**Card `55b459c0`, answered 2026-10-05T11:17:59Z — the two findings no earlier answer covered.** These are the
answers that close §11's "Still open" list on the contract side. Both are **acceptance of a known risk**, and
Counsel's recommended route for each was the opposite one, so each row says what was declined as well as what was
accepted.

| Question | His answer | What it settles | What it does **not** settle |
|---|---|---|---|
| **Our model account is unpaid, so the provider's Terms let our content be used to improve their service. Do you accept that second purpose?** | **`accept_second_risk`** — "Accept it knowingly and record it as a second known risk" | **CR6 becomes an owned, recorded risk** (§10.1), logged as a *second* risk so it cannot hide inside the transfer exposure Chris already accepted. He has now answered the question on his card, so it is a decision rather than a gap | It does not supply a **lawful basis** for the improvement purpose, and it does not make the purpose **disclosable** in §8.2's notice. **It is also untouched by `do_it_now` Art. 46 work** — a Chapter V safeguard cannot cure a second purpose. Whether the provider exercises the right stays **UNKNOWN and unverifiable** |
| **The provider's Terms have us warrant that we hold "all rights, licenses, and permissions needed" to send the input. Client archives are full of named third parties we did not collect. Do you accept that exposure?** | **`accept_warranty_risk`** — "Accept the warranty exposure and record it as a known risk" | **CR2 becomes an owned, recorded risk** (§10.1). Counsel's fix — a matching client warranty, §10.3 clause 3 — is **declined for now**, and the draft is marked not-adopted so nobody offers it by accident | It does not make the warranty **true**, it does not **withdraw** it (the Terms admit no customer withdrawal), and it does not resolve **breach status**, which stays **UNSURE**. Accepting an exposure is not a finding that no breach has occurred |

**Acceptance is not a waiver — the six duties that survive it, unchanged.** These are the points Counsel raised
before the answers came back, updated where an answer has landed. None of them is a fine. Each is a duty, and none
of them scales with risk appetite. **All four of Chris's acceptances are on the record; not one of them discharges
anything below.**

1. **Art. 13(1)(f) still requires disclosure — and the disclosure is now of a known deficiency.** The notice we owe
   (§8.2) must tell data subjects that their data is transferred to a third country. The truthful version must also
   say that transfer has **no Art. 46 safeguard behind it and an unnamed processor**. A client agreeing to a transfer
   is not a disclosure to a data subject, and telling a data subject is not the same as a client agreeing.
2. **Art. 30(2)(d) still requires the record.** The truthful entry in the processing register is "third-country
   transfer, United States, **no Art. 46 safeguard in place, processor unnamed**". **A record cannot record
   acceptance instead of the truth.**
3. **Art. 32 security and Art. 33 breach notification are untouched**, and Security's findings (§2, §5, §6, §7) are
   the evidence for both. Art. 33 is the one with a clock on it: 72 hours, "without undue delay" not "next business
   day".
4. **The contract risk and the regulatory risk do not substitute for each other.** Accepting the GDPR exposure did
   not authorise the contractual breach; and now that the breach is accepted knowingly, this file says so in terms —
   which is different from saying it was lawful.
5. **The second processing purpose (CR6) is accepted and still unlawful-basis-free.** `accept_second_risk` owns the
   risk. It does not create a lawful basis for the improvement purpose, and **no Art. 46 work can reach it**,
   because a second purpose is not a transfer. Two follow-on duties are now owed rather than merely noted: **the
   Art. 30 record must state the purpose** rather than record acceptance in place of it, and if the purpose is ever
   confirmed to be in use, **§8.2's notice has to be corrected to disclose it** — or the improvement purpose has to
   stop.
6. **The rights warranty (CR2) is accepted and still being given.** `accept_warranty_risk` owns the exposure. The
   representation goes out on **every input we send**, so acceptance is a decision to keep making a statement we may
   not be able to support. It changes no contract term, and while **breach status is UNSURE** we do not know whether
   this is a live breach or a contingent one. **It is also the item most likely to be quietly reversed by a new
   client contract**: the moment we sign any client, §10.3 clause 3 is the one-line fix, and it should be picked up
   again rather than treated as settled.

**The honest summary of the contract position after four answers.** Chris has accepted four risks knowingly, on the
record, with his name on them: CR1, CR2, CR5, CR6. **That is a legitimate place for a one-person company to put
things, and it is not a licence to stop looking.** The pattern worth naming is that three of the four are things we
*do not control* — a provider's Terms, an unnamed processor, a stealth model's free tier — and the two cheapest fixes
for all of them (clause 2 and clause 3 in §10.3) cost nothing but a client conversation. **They are declined for
now, not rejected.** Counsel's recommendation stands on the record so that if the exposure ever converts into an
actual claim, the next reader can see the option was available and priced.

### 10.3 Draft contract clauses (DRAFT — not legal advice, not for signature)

Counsel drafts; Counsel does not sign. Marked draft per instruction.

**Status of these three drafts, as of 2026-10-05: none of them is adopted, and none may be offered to a client in
this revision.** Read the table before the clauses, because a draft that is not marked here could be mistaken for
text we intend to use.

| Clause | Intended to close | Status | Why |
|---|---|---|---|
| **1 — International transfers** | §10's Art. 46 gap in the client contract | **Must not be offered as drafted** (see below). Repair (a) is Counsel's recommendation; repair (b) is Chris's undecided commercial call | It promises an Art. 46 safeguard we cannot keep at the model layer, and Chris accepted the exposure without accepting a false statement to a client |
| **2 — No third-party content at the model layer** | CR1, cleanly and on either reading of the clause | **Drafted, not adopted** — declined in favour of `accept_breach` on CR1 | Accepting the breach removed the trigger that made this clause worth asking a client for. **Still the cheapest fix available** if that decision is ever revisited |
| **3 — Client authority to process** | CR2, and CR1 as a side effect | **Drafted, not adopted** — declined in favour of `accept_warranty_risk` on CR2 | Counsel's recommended route for the rights warranty. Chris chose acceptance instead, so this is **not** to be offered, and a client must not be asked to warrant its own rights on this basis without Chris saying so |

**Keeping a declined draft in the file is deliberate, and here is the reasoning so it is not mistaken for
inaction.** These three clauses are the only options that cost no money, need nothing from the provider, and need no
engineer. They were declined as a **risk-appetite** decision, not because they are wrong. If CR2 or CR6 ever
converts from an accepted risk into an actual claim, a regulator question, or a client audit, the file already holds
the cheapest available response and records what it would have taken. **What is not permitted is quietly sending
clause 2 or clause 3 to a client because they are already written.**

**Clause 1 — International transfers (carried forward, with a problem that only became visible after the answers).**

> **International transfers.** The Service Provider processes Personal Data outside the
> European Union and the European Economic Area only where the Client has agreed in writing to
> such processing. The Service Provider shall identify in writing, before the transfer begins,
> each recipient and the country in which it processes Personal Data, and shall put in place
> before that transfer the appropriate safeguards required by Article 46 of Regulation (EU)
> 2016/679. The Client's agreement under this clause does not discharge the Service Provider's
> own obligations under Article 46, and the Service Provider shall not treat it as doing so.

That last sentence is deliberate. Without it a client can read the clause as a promise that they have discharged our
regulatory duty, which is exactly the assumption that fails in an audit.

**The problem.** As drafted, this clause promises the client that the Service Provider "shall put in place before
that transfer the appropriate safeguards required by Article 46". **We cannot keep that promise at the model layer**,
and every client-data agent runs at the model layer (§4, §10). Chris accepted the *exposure* — he did not accept
making a statement to a client that we know to be untrue. **So this clause must not be offered in this form** while
§4 rule 3 is unmet for every provider. Two honest repairs:

- **(a) restrict** — the clause applies only to a recipient we have named, in a country we have named, with an Art. 46
  mechanism in place **before** the transfer. In practice: no client personal data to the model layer until the
  provider is named and the mechanism exists. **Counsel's recommendation.**
- **(b) disclose the gap** — keep the clause and add the client's express acknowledgement that the transfer happens
  with no Art. 46 safeguard. This is what §8.2's notice will have to say anyway, so at least it is consistent.
  **It is still a promise to process in a way we have already accepted we cannot, and it hands the client the
  argument.** Counsel does not recommend it. It is Chris's call because it is a commercial and liability decision,
  not a drafting preference.

**Clause 2 — No third-party content at the model layer** (the operational form of "clean on either reading").
**NOT ADOPTED — see the status table above. Do not offer this to a client without Chris's express instruction.**

> **Third-party personal data.** The Service Provider's processing of Personal Data depends on which model provider
> receives it, and not every model provider can be identified by name in advance. The Client instructs the Service
> Provider not to place the personal data of any individual who is not the Client or the Client's personnel into any
> model layer that the Service Provider cannot identify by name and by country of establishment, until the Service
> Provider has put in place the safeguards required by Article 46 of Regulation (EU) 2016/679. This instruction is
> limited to such model layers and does not restrict the Service Provider's use of its own systems.

**Clause 3 — Client authority to process** (drafted to close CR2; closes CR1 as a side effect). **NOT ADOPTED —
see the status table above. Do not offer this to a client without Chris's express instruction.**

> **Client authority to process.** The Client represents and warrants that it holds all rights, licenses, consents
> and permissions necessary to instruct the Service Provider to process the Personal Data for the purposes of this
> Agreement, **including to transfer that Personal Data to a sub-processor or model provider outside the European
> Union or the European Economic Area**, and that doing so will not infringe the rights of any third party. Where the
> Personal Data includes the personal data of individuals who are not the Client, the Client will identify them to
> the Service Provider in writing before any such transfer and will obtain and evidence any consent that transfer
> requires.

Counsel's note on clause 3: a client that warrants its own rights is also a client whose data we are entitled to
pass onward, so this single clause answers both the rights warranty **and** the clean-on-either-reading problem in
CR1. It is the cheapest clause in this section and the only one that needs nothing from the provider. **That is why
it is the draft most likely to be revived: it needs no provider cooperation, no engineering and no money — only a
clause in a contract we have not yet signed.** Chris declined it for now (§10.2); Counsel's assessment is that it
remains the highest-value per-word option in this file, and that this is a deferral, not a rejection.

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
| **Running client work through the model, against the provider's third-party-use clause** | **`accept_breach`** — "Knowingly accept the contract breach" | CR1 is an owned contract risk (§10.1). It does **not** become permitted, and it hands the provider a contractual ground to suspend us under CR3 (§10.2) |
| **Who the provider's Terms bind — the business, or Chris** | **`accept_personal`** — "Accept it and record it as a known risk" | CR5 is recorded as a known risk on Chris. **We are not restructuring through the business, so the forfettario position is untouched** (§10.2) |
| **The rights warranty we cannot honour** (CR2) | **`accept_warranty_risk`** — "Accept the warranty exposure and record it as a known risk" | CR2 is an owned contract risk (§10.1). Counsel's fix, the client warranty in §10.3 clause 3, is **declined for now and marked not adopted**. Breach status stays **UNSURE** and the representation is still given on every input |
| **The second processing purpose on an unpaid account** (CR6) | **`accept_second_risk`** — "Accept it knowingly and record it as a second known risk" | CR6 is an owned risk, recorded as a **second** one so it does not hide inside the accepted transfer. **No lawful basis has been identified, no notice discloses it, and `do_it_now` Art. 46 work cannot reach it** — a second purpose is not a transfer (§10.2) |

**Every finding in the §10.1 register now has an owner.** CR1 `accept_breach`, CR2 `accept_warranty_risk`, CR5
`accept_personal`, CR6 `accept_second_risk`. **CR3** (unlimited suspension right) and **CR4** (uncapped indemnity)
were never put to Chris and are not decisions — they are the standing exposure that comes with using an unnamed,
stealth model provider, and they are recorded here so that "every finding has an owner" is not read as "every finding
has been accepted". CR3 and CR4 need no decision to be true.

### Asked 2026-10-05, and answered 2026-10-05T17:31:05Z

**Read this before acting on §6 or §8.3.** Three client-data questions were put to Chris on card `eaaf3ab1` on
DIG-921 (`human_only`, created 13:20:17Z). **Chris answered all three at 2026-10-05T17:31:05Z.** They were first
raised on card `62b13d4d` on DIG-893, and **that card was expired with `outcome: issue_closed` and `answers: []`
at 2026-10-05T13:12:24Z** — four seconds after DIG-893 was closed, because closing an issue expires its open
cards. Chris never saw the first one. **Only the `eaaf3ab1` answers count. Card `62b13d4d` is dead and must
never be recorded as an answer.**

| # | Question put to Chris | Counsel's recommendation | Where the answer goes | **Chris's answer** |
|---|---|---|---|---|
| q1 | May the next client dataset land before the DPIA's 14 measures are built? | `wait` | §8.3 gate statement | **`wait`, 2026-10-05T17:31:05Z** |
| q2 | Do we stop pushing snapshot refs to the public remote? | `stop` | §6, owned by DIG-784 | **`stop`, 2026-10-05T17:31:05Z** |
| q3 | Do we prepare an external DPO, or accept the exposure? | `accept`, with a re-open trigger | the register below | **`prepare`, 2026-10-05T17:31:05Z** — **not Counsel's recommendation** |

**No agent answered that card.** Chris did, on the Decisions board, under `human_only`. Counsel's picks had been
recorded in `decisions/recommendations.jsonl` as recommendations and were deliberately kept out of the "Decided"
table until he actually answered; a recommendation read back as a decision is the failure this section exists to
prevent. **He took the recommendation on q1 and q2 and overrode it on q3. His answers are the record.**

**q1 and q2 came in as recommended, which means the safe posture is now the decision and not only the
default.** The next client dataset does not land until DIG-912's filter exists. Snapshot refs stop going to the
public remote under DIG-784. **What neither answer does is shrink the 74 refs already published** (§6).

**What is waiting, and on whom.** q1's wait ends on **DIG-912** (CTO, `in_progress`) — the Art. 9 filter — so the
wait is neither open-ended nor a lost client. q2 is executed by **DIG-784** (Security, `in_progress`). **q3 is
not a wait at all: Chris chose to spend money, so it becomes work with an owner** (see the register entry below).

### Still open

**Both contract findings left this list on 2026-10-05** — CR2 as `accept_warranty_risk` and CR6 as
`accept_second_risk`, recorded in the table above and in §10.2. **All three client-data questions left this list
on 2026-10-05** — `wait`, `stop`, `prepare` — so no item below is on Chris's card. The rest are Counsel's own open
work, one item that needs an owner (the external DPO), and questions that have never been put to him.

- **Whether any candidate provider will sign Art. 46 safeguards.** Not asked yet (§10). Counsel's view: ask **one**
  provider in writing, before building anything else. A signed SCC set from one provider is worth more than a
  completed questionnaire from three.
- ~~**Whether a DPIA is required before the next client dataset lands.**~~ **CLOSED 2026-10-05 — the answer is
  yes, CONFIRMED**, and the assessment is written down. `knowledge/dpia.md`, published on DIG-893. §8.3 was
  rewritten to match. **What stays open is narrower and is Counsel's own work:** whether an Art. 9(2) exception
  covers what we actually do (**UNKNOWN** — it turns on a client dataset the assessment has not seen), and whether
  the measures the assessment lists get built. **The gate on the next dataset is Article 9, not Article 35** —
  a DPIA cannot create an exception, so "do a DPIA" was never the real blocker. **Counsel's assessment is
  complete. **Chris gave that go-ahead on 2026-10-05 and it was `wait`** — card `eaaf3ab1`, 17:31:05Z, so the
  next dataset waits on DIG-912 (§11, §8.3).**
- ~~**The Art. 37(1)(c) DPO question — UNSURE.**~~ **ANSWERED 2026-10-05T17:31:05Z: Chris chose `prepare`.**
  No DPO is designated, which does not by itself breach Art. 35(2). If "large scale" Art. 9 processing is
  conceded, **Art. 37(1)(c) arguably obliges one**, and Art. 37(6) allows an external DPO — the realistic route
  for a sole freelancer. Counsel cannot say the duty applies, because it turns on the same large-scale fact that
  is itself unsettled. **Chris was asked to accept that uncertainty for free and chose instead to buy it out.**
  The accepted-risk framing is therefore **not** what happened, and this entry is a work item, not a register
  entry:

  > **DECISION, q3, 2026-10-05, Chris — `prepare` an external data protection officer.** This is the one
  > question of the three where he did not take Counsel's recommendation. Counsel's pick was `accept` and the
  > reason it was free was that the duty was UNSURE; his answer spends money to remove the uncertainty rather
  > than live with it. **The label stays UNSURE.** Preparing an officer does not make Art. 37(1)(c) apply and
  > does not make it not apply — it is a risk-appetite decision, not a legal finding.
  >
  > **What `prepare` does not do:** it does not designate anyone. Art. 37(1) is a designation duty and Art. 38(1)
  > requires the officer be involved in all matters relating to the protection of rights and freedoms — neither
  > is met by getting ready. Art. 37(6) permits an external person "to fulfil the tasks on the basis of a service contract", which
  > is the route Chris's answer implies; Art. 38(2) requires the controller to support the officer's resources,
  > which is a standing cost, not a one-off. **And it does not remove the re-open trigger below.**
  >
  > **What `prepare` commits:** money. Counsel cannot spend it, sign anything, or pick a provider, and this
  > entry is **not** authority to engage anyone. It is a decision that the work should be scoped and costed.
  >
  > **Re-open trigger (carried over, and it still binds).** If digithings ever processes large-scale Art. 9 data
  > — which is, if q1 ever moves off *wait* — the Art. 37(1)(c) question reopens **before** we process, not
  > after. On the `prepare` answer this is no longer the trigger for accepting risk; it is the trigger for
  > **completing** the engagement. Reading the two answers together: q1 `wait` keeps the large-scale question
  > closed, and `prepare` means the money is spent only if it opens.
  >
  > **Re-open trigger for `prepare` itself.** If no external officer is engaged by the time q1 moves off *wait*,
  > this decision has been overtaken by events and comes back to Chris with a cost attached.
  >
  > **Owner, filed 2026-10-05: DIG-1107**, "Prepare (draft, do not sign) the external DPO engagement". It carries
  > the DRAFT instrument of appointment, the requirements brief, the cost range, and the one numbered money
  > question for Chris. Until DIG-1107 lands there is **no owner and no budget line** for this decision, and a
  > decision with neither is one that quietly does not happen.
- **The Art. 14 question.** Whether we owe notice to data subjects in client-supplied data we did not collect from
  them. Counsel has not verified Art. 14's text this run. **UNSURE.**
- **Where the four workspace-only legal artefacts live.** `privacy-notice.md` (§8.2), `processing-record.md`
  (§8.1), `provider-transfer-register.md` (§10) and `prelaunch-legal-inventory.md` exist only under
  `~/paperclip-workspace/knowledge/`. **Counsel has deliberately not moved them into the repository**, which has a
  public GitHub remote, and will not without Chris saying so — they name the client's contractual posture and our
  known gaps. See "Where this page lives".

**On what he accepted rather than fixed** — the working-files gap (§7), the model-layer exposure (§4), and the four
contract findings CR1, CR2, CR5 and CR6 (§10.2) — the honest reading is that they are **known, accepted risks with a
named owner**, which is a legitimate place for them to be. **They are not fixed, and this page does not imply they
are.** And acceptance is not permission: §10.2 lists the six duties that survive it untouched. **Six accepted risks,
no repairs, and a decision log that is complete — that is what this page now records, and it is a smaller thing than
it sounds.** The repairs that would retire the two contract findings cost nothing and are drafted (§10.3, clauses 2
and 3); they wait on Chris, not on engineering, not on a provider, and not on a budget.

---

## Where this page lives

**One copy, and this is it.** This file — `/Users/chrisstefan/Code/digithings/knowledge/data-policy.md` — is the
authoritative copy, and it is also published as the `data-policy` document on this issue so the board reads the same
text Counsel does.

Until 2026-10-05 a **second, divergent copy** existed at `~/paperclip-workspace/knowledge/data-policy.md`. It was not
a stale duplicate of a finished page. It carried the entire provider-Terms analysis that the published copy was
missing, while the published copy carried Security's four answers that the workspace copy was missing. **Two versions
of a legal document is itself a risk**: a client, a reviewer or the next agent can be shown either one, and they
disagree. Both paths now hold identical bytes, verified after the write, and the analysis is merged into §10.

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
| Art. 37(1) is a designation duty; Art. 38(1) involvement; Art. 38(2) resources; **Art. 37(6) permits an external DPO** | **CONFIRMED** as to substance | GDPR 2016/679, Arts. 37–38, read 2026-10-05. Read again on 2026-10-05 because Chris's `prepare` answer makes them load-bearing: **Art. 37(6) is the clause that makes an external officer lawful for a sole freelancer** — "The data protection officer may be a staff member of the controller or processor, or fulfil the tasks on the basis of a service contract". Art. 38(3) is the independence guarantee (no instructions, no dismissal, direct report to the highest management level) and was **previously mis-cited on this page as the external-DPO clause; corrected 2026-10-05** |
| **A DPIA is required before the next client dataset** | **CONFIRMED** — **moved off LIKELY 2026-10-05** | `knowledge/dpia.md`, DIG-893. 7 of 9 WP248 rev.01 criteria met against a 2-criterion threshold; Garante provv. 467/2018 Allegato 1 item 7 on its face; Art. 35(1). No Art. 35(5) exclusion exists. This replaces the old LIKELY row |
| **The gate on the next dataset is Article 9, not Article 35** | **LIKELY** | A DPIA documents and mitigates risk; it cannot create an Art. 9(2) exception. `knowledge/dpia.md` §7 |
| Art. 36 prior consultation with the Garante is **not yet owed** | **LIKELY** | Art. 36(1) triggers on high risk "in the absence of measures taken by the controller to mitigate the risk". Measures are not built. Becomes owed only if residual risk is still high afterwards. `knowledge/dpia.md` §8 |
| Art. 37(1)(c) obliges a DPO if "large scale" Art. 9 processing is conceded | **UNSURE** | Art. 37(6) permits an external DPO. Art. 37(4) optional designation where 37(1) does not apply (read 2026-10-05); Italy has not extended it to us — not verified. `knowledge/dpia.md` §5 |
| Whether the next client dataset may land (q1) | **DECIDED — `wait`, Chris, 2026-10-05T17:31:05Z** | Card `eaaf3ab1` on DIG-921, `human_only`, `resolvedByUserId: local-board`. No agent answered it. Card `62b13d4d` on DIG-893 expired unanswered (`outcome: issue_closed`, `answers: []`) at 13:12:24Z and is not a source. §11 |
| Whether to stop pushing snapshot refs to the public remote (q2) | **DECIDED — `stop`, Chris, 2026-10-05T17:31:05Z** | Same card. **Forward-looking only — the 74 refs already on the public remote stay clonable** (§6). No owner exists for scrubbing them |
| Whether to accept the DPO exposure or prepare an officer (q3) | **DECIDED — `prepare`, Chris, 2026-10-05T17:31:05Z. Not Counsel's recommendation** | Same card. Counsel recommended `accept` with a re-open trigger. **`prepare` spends money and does not change the Art. 37(1)(c) label, which stays UNSURE.** Counsel did not and cannot spend, sign or pick a provider |
| The next client dataset does not land until the measures are built | **CONFIRMED that the gate is Art. 9; LIKELY no exception identified; UNKNOWN whether one covers us. Now also DECIDED, as `wait`** | Counsel's own assessment, `knowledge/dpia.md` §7 and §8.3, plus Chris's `wait`, 2026-10-05T17:31:05Z. **The legal basis was Counsel's finding and was not decided by Chris; the wait is his decision and rests on it** |
| The Digital Omnibus relaxes the Art. 35 DPIA obligation | **CONFIRMED THAT IT DOES NOT — it is a proposal, not law** | COM(2025) 837, 19 Nov 2025, proc. 15698/25, still in negotiations 2026-10-05. Presidency compromise recital 40 keeps Art. 35(1)'s "high risk" trigger intact |
| WP248 rev.01's nine criteria and the two-criterion rule | **CONFIRMED** | Two independent reproductions: Garante provv. 467/2018 preamble (Italian) and the EDPB-hosted `it_dpia_blacklist.pdf` (English). **WP248 itself was not read directly** — three fetches returned challenge pages. Recorded as a sourcing limitation |
| Whether an Art. 9(2) exception covers what we actually do | **UNKNOWN** | Turns on the client's actual processing, which the assessment has not seen. `knowledge/dpia.md` §7 |
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
| **Credential scanning covers `projects/*/vault/`** | **CONFIRMED THAT IT DID NOT — FIXED 2026-10-06 on DIG-785** | `.gitleaks.toml:39–42` allowlisted `^projects/[^/]+/vault/`; path exemption deleted and replaced with a single-commit entry. New vault files are scanned |
| **Two secret redactors exist and neither is Art. 9** | **CONFIRMED** | `digitrace/redaction.py` (3 regexes, LangSmith egress only, inert without `LANGSMITH_API_KEY`); `digibase/audit.py` (key-name based) |
| Whether an Art. 46 mechanism exists today | **UNKNOWN** | Not found in the repo; may exist in client paperwork. Chris has ordered the work |
| Whether a candidate provider will sign Art. 46 safeguards | **UNKNOWN** | Not yet asked |
| Retention periods | **DECIDED, not yet enforceable** | Chris `d90_30_split`; §6 shows two stores with no retention today |
| The rights-warranty exposure (CR2) is accepted | **DECIDED** | Chris, card `55b459c0`, `accept_warranty_risk`, 2026-10-05T11:17:59Z. Whether we already breach stays **UNSURE** — the decision is about the exposure, not the breach status |
| The second processing purpose (CR6) is accepted | **DECIDED** | Chris, card `55b459c0`, `accept_second_risk`, 2026-10-05T11:17:59Z. Whether the provider exercises the right stays **UNKNOWN and unverifiable**; no lawful basis has been identified |
| Acceptance creates a lawful basis, permits the breach, or cures a transfer | **CONFIRMED THAT IT DOES NOT** | Acceptance is a risk-appetite decision. §10.2 item 1–6; Art. 6 and Art. 46 are not in our gift to waive, and the provider's Terms admit no customer withdrawal |

| Provider Terms — improvement-use, third-party-use, rights warranty, suspension, indemnity and counterparty clauses | **CONFIRMED as text** | `https://opencode.ai/legal/terms-of-service`, effective Aug 15 2026, read 2026-10-05; counterparty ANOMALY INNOVATIONS, INC. |
| Whether running client work **breaches** the third-party-use clause | **LIKELY** no-breach, **not CONFIRMED** | The deciding words are "or for the benefit of any third party", and an arbitrator can read them literally (§10.1) |
| Whether we already **breach** the rights warranty | **UNSURE** | Turns on whether "permissions needed" reaches processor sub-processing; the Terms do not answer it |
| Whether the liability cap reaches the indemnity **we owe** | **UNSURE** | Flagged, not asserted. The cap is drafted as a limit on liability to us |
| Which individual the Terms bind | **UNSURE** | No digithings Zen account exists, and no individual acceptance record has been located |
| Our model account is **unpaid**, so the improvement-use clause is textually live | **CONFIRMED** | Direct experiment 2026-10-05: `space-bunny-free` → HTTP 200, `"cost":"0"`, **no `Authorization` header**; paid models → 401 without a key, 402 "Insufficient account funds" |
| Whether the provider **exercises** the improvement right | **UNKNOWN**, and unverifiable from outside | No account, plan or usage endpoint exists; every one probed returned 404 |
| `space-bunny-free` is absent from the provider's own zero-retention exception list | **CONFIRMED** | `/docs/zen` Privacy block enumerates nine exceptions; this model is not among them. A documentation page, not the binding Terms |
| Art. 5(1)(b) / Art. 6 numbering behind the second-purpose finding (CR6) | **UNSURE** | Article numbers only, text not re-verified this run. The conclusion does not depend on the numbering |

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

**Advice only. Counsel signs and sends nothing. Twelve-x stays anonymous. Chris has decided every question put to
him — eleven in §11 and four in §10.2, across three cards on 2026-10-05. Six are accepted knowingly rather than fixed:
the working-files gap (§7), the model-layer exposure (§4), and the four contract findings CR1, CR2, CR5 and CR6
(§10.2). Four controls in this page are known to be weaker than revision 1 claimed. **Nothing is waiting on him
silently and nothing in this page records an answer he did not give.** The three client-data questions on card
`eaaf3ab1` were answered at 2026-10-05T17:31:05Z — `wait`, `stop`, and `prepare`, **the last against Counsel's
recommendation**, recorded as his answers and not as Counsel's picks. The other open items were never on his card,
and the DPIA question was answered by Counsel's own assessment (§8.3, `knowledge/dpia.md`), with the Art. 9
measure it found to be the real gate tracked as DIG-912, assigned to the CTO. The repairs that would retire CR2
and CR6 are drafted, cost nothing, and wait on him (§10.3). The DPIA is written and is a draft for him to take up;
it says the next client dataset is gated on Article 9, not on Article 35 — **and on his `wait` answer it does not
land.** The external DPO he chose to prepare is **not** on a card and has no owner yet.
**This page is not a compliance record.**