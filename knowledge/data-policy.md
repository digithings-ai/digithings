# digithings client data and data protection policy

One page. What we keep, how long, which models may see it, what is anonymised, how deletion works, who may touch it.
Written by Counsel with Security, 2026-10-05. Decision owner: Chris.

**Status: DRAFT — 3 decisions open, see the end. This page is advice. It is not a compliance record and it does not
by itself satisfy any GDPR obligation.**

Client is referred to by codename only. **twelve-x stays anonymous in every artefact, including this one.**

---

## 0. The two findings that matter most

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
**We have no record of an Art. 46 mechanism for any provider.** UNSURE whether one exists outside the repo — see
Decision 2.

**0.3 — Free tiers train on data.** The snapshots record `trains_on_free_tier: true` for Mistral and others. A
free-tier key pointed at client correspondence is provider training on client personal data. **Prohibited here,
no exceptions.** CONFIRMED by catalogue read 2026-10-05.

---

## 1. What we keep

| What | Why we hold it | Lawful basis | Confidence |
|---|---|---|---|
| Client exports (chat logs, email threads) | Feeding the client's own agents | Client's instructions — **Art. 28 processor** | LIKELY, see Decision 1 |
| Derived agent artefacts (summaries, embeddings, thread state) | Same | Same | LIKELY |
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
(Art. 9(2)), not a permission. **There is no Article 9 detection or redaction step anywhere in our pipeline
today.** CONFIRMED by repo search 2026-10-05.

This is the most serious operational gap in this page, and it is worse than the retention question: a retention
period bounds how long we hold Art. 9 data, but with no filter we may be *collecting* it without an exception in
the first place. **Reading a client's whole inbox is a bigger legal step than reading a support ticket.**

## 3. How long

**No retention period is set anywhere in our files.** CONFIRMED by repo search. Art. 5(1)(e) requires:

> "Personal data shall be … kept in a form which permits identification of data subjects for **no longer than is
> necessary** for the purposes for which the personal data are processed."
> — **GDPR Art. 5(1)(e)**. CONFIRMED.

| Dataset | Proposed retention | Basis for the cutoff |
|---|---|---|
| Client exports | Duration of engagement + **30 days**, then deletion | The purpose ends with the engagement |
| Agent-derived artefacts | Same as the export they came from | No point outliving the source |
| Run logs and traces | **90 days** | Enough to debug and reconstruct; Art. 22 automated-decision risk drops once the trace is gone |
| Invoices, contracts, tax records | **10 years** | Italian civil/fiscal retention; Art. 17(3)(b) and (e) exceptions — legal obligation and legal claims. **Not ours to shorten.** |

**The 90-day trace retention is also what keeps us clear of Art. 22.** Art. 22(1) gives a data subject the right
"not to be subject to a decision based solely on automated processing, including profiling, which produces legal
effects… or similarly significantly affects him or her." CONFIRMED. Short trace life is not a full answer to
Art. 22, but it bounds it.

**Deletion cannot be promised to a client as a contractual commitment until Decision 3.** Do not put a deletion
guarantee in a contract before the schedule above is agreed.

## 4. Which models may see client data

**Rules, in order of application:**

1. **Only providers with `zero_retention_on_paid: true` in our own catalogue** — currently mistral, gemini,
   openai-with-ZDR-add-on. A model absent from `docs/providers/snapshots/` is **not approved**, regardless of what
   anyone believes about it.
2. **Paid tier only.** Free tiers train on data (§0.3).
3. **EU/EEA-established provider only, unless Decision 2 puts an Art. 46 mechanism in place first.** Domicile is
   unrecorded in our catalogue for every provider (§0.2), so on today's evidence **no provider is yet affirmatively
   approved under this rule.** Treat the candidate list as Mistral paid, pending the entity check.
4. **No client data on a model we cannot name in the catalogue.** This currently excludes Space Bunny and LongCat
   (§0.1). They may well have acceptable terms — **we have not checked, and "not checked" is not "approved".**
5. **twelve-x and all client codenames are pseudonymised before any prompt leaves our infrastructure** (§5).

**On today's evidence rule 3 is unmet for every provider, so the honest position is that no job may yet send
client personal data to any external model.** That is uncomfortable and it is the accurate reading of what our
artefacts support. It is a gap to close this month, not a reason to guess.

**If these rules cannot all be satisfied for a job, the job needs a decision from Chris — not a workaround.**
That is the honest reading of Art. 5(1)(b) purpose limitation and Art. 5(1)(c) data minimisation together.

## 5. What gets anonymised before anything goes to another model

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

| Do | Do not |
|---|---|
| Replace personal names with stable per-run tokens | Send real names "because the model needs context" |
| Strip email addresses, phone numbers, account and payment identifiers | Send a thread with the address headers intact |
| Replace employer and client names with codenames | Send `twelve-x` or a client name in any prompt |
| Drop attachment bodies not needed for the task | Bulk-embed an inbox |
| Log the **pseudonym key** separately, access-controlled | Put the pseudonym key in the same log |

**Limitation, stated plainly:** pseudonymisation is a security and minimisation measure, **not an exit from the
GDPR.** Recital 26 treats pseudonymised data as still personal data. Anonymised data is out of scope; we do not
currently claim to produce it. **UNSURE** whether our pseudonym key storage meets the Art. 32 standard — that is
a Security question, raised below.

## 6. How deletion works

**The data subject's right is absolute in form and qualified in substance.** Art. 17(1)(a) CONFIRMED: erase where
"the personal data are no longer necessary in relation to the purposes for which they were collected or otherwise
processed". Two exceptions matter to us: Art. 17(3)(b) legal obligation, and Art. 17(3)(e) legal claims — the
tax and invoice rows in §3.

**Deletion must reach five places, and we can currently demonstrate two:**

| Where | Status |
|---|---|
| The export file | **CONFIRMED** — it is a file, so it can be deleted |
| Our derived artefacts | **CONFIRMED** — files, deletable |
| Thread state and embeddings in the database | **UNKNOWN** — not verified |
| Provider-side copies | **Out of our hands** — mitigated only by zero retention (§0.1/0.2) |
| Backups and snapshots | **UNKNOWN** — `dt-snapshot` commits exist; a deleted file can return in a later snapshot |

**The snapshot finding is real and I will not paper over it.** `knowledge/oss-policy.md` and this page both
appear in `dt-snapshot` commits, so the repo is snapshotted automatically. **A deletion that does not account for
snapshots is not a deletion.** CONFIRMED that snapshots exist; UNSURE how they are pruned.

## 7. Who may touch it

- **Chris** — client data of his own clients, as the party who signs.
- **Named engineers on that engagement only** — least privilege, per Art. 32(1)(b) CONFIRMED
  ("the ability to ensure the ongoing confidentiality… of personal data").
- **Agents** — only on pseudonymised data, per §5.
- **OSS Researcher and contractors** — **no access to `projects/*` client data.** The repo's `.gitignore`
  already anchors private client projects as never-committed (lines 40, 148); that is the control to rely on,
  not an assumption. CONFIRMED the rule exists.
- **Not Security's problem to hold a copy.** Technical controls are queried without exporting the data.

## 8. Three obligations we do not currently meet

These are not policy gaps. They are missing artefacts.

**8.1 — No record of processing activities.** Art. 30(1) CONFIRMED: "Each controller and, where applicable, the
controller's representative, shall maintain a record of processing activities under its responsibility." The
small-organisation exemption in Art. 30(5) applies only where processing is **occasional**, or **low-risk**, or
does not include Art. 9 data. Reading clients' correspondence routinely is none of those three. **The exemption
is unavailable and we need the record.** LIKELY.

**8.2 — No privacy notice.** Art. 13(1) CONFIRMED requires the controller to give the data subject identity and
contact details, purposes, legal basis, recipients, retention period and data-subject rights "at the time when
personal data are obtained". If the client is the controller, the client gives this and we are named as processor.
If we hold data as a controller in our own right (§Decision 1), **we owe our own notice and have none.**
UNSURE which we are — that is Decision 1.

**8.3 — No DPIA, and one may be required.** Art. 35(1) CONFIRMED requires an impact assessment *before* processing
where it "is likely to result in a high risk", having regard to "the nature, scope, context and purposes of the
processing". Routinely reading clients' email, on a public AI platform, with Art. 9 content and international
transfers, is a plausible high-risk case. **We should assume a DPIA is required before the next client dataset
lands, not after.** LIKELY, not CONFIRMED — this needs a real risk assessment, not my reading of one clause.

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

---

## Decisions for Chris

These are the three that only he can make. Each one changes the architecture, not just the paperwork.

**Decision 1 — In what capacity do we hold client data?** Processor on the client's instructions, or a separate
controller in our own right? This single answer determines whether Art. 28 applies, whether we owe an Art. 13
notice, whether the Art. 30 record is ours, whether a DPIA is owed, and whether a client can demand deletion on
offboarding. *Counsel's view: as a platform we will drift toward controller. Deciding it deliberately is cheaper
than discovering it in a client audit.*

**Decision 2 — May client data leave the EU/EEA?** If yes, who signs the Art. 46 transfer mechanism, and on what
terms — does the client have to accept it in the contract? If no, **we need each candidate provider's domicile
recorded before any of them is approved**, and job feasibility then depends on a single provider. *This is a
commercial decision as much as a legal one, and it is the one most likely to be forced on us by a client's own
security questionnaire — which is the right time to have already answered it.*

**Decision 3 — Do we offer clients a deletion commitment, and on what period?** The schedule in §3 is a proposal.
A contractual deletion guarantee to a client is a commitment we could be held to on a period we have not yet
agreed internally. *Counsel's view: offer one, at the §3 numbers, once Security has confirmed the third
retention gap. Do not offer it before.*

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
| Controller vs processor status | **LIKELY** | Turns on Decision 1 |
| Art. 30(5) exemption unavailable | **LIKELY** | Turns on whether processing is occasional/low-risk |
| A DPIA is required before the next dataset | **LIKELY** | Turns on a real risk assessment, not this page |
| Snapshot deletion gap | **CONFIRMED** snapshots exist / **UNSURE** how pruned | `dt-snapshot` commits |
| Database, embedding and backup deletion | **UNKNOWN** | Not verified — Security question |
| Whether an Art. 46 mechanism exists today | **UNKNOWN** | Not found in the repo; may exist in client paperwork |

**Sourcing limitation, recorded for honesty.** EUR-Lex was unreachable from this session (HTTP 202 bot challenge on
every attempt, 2026-10-05). The article text above was read from a reproduction of the Regulation, and
cross-checked against the UK consolidated text on legislation.gov.uk. **Both are copies, not the Official Journal.**
Chapter V (transfers, Art. 44–49) is the area where national derogations and amendments matter most, so the
transfer reasoning in §0.2 and Decision 2 should be confirmed against the current consolidated EU text before it is
relied on externally. I have not asserted CONFIRMED on anything I read in only one copy.

---

**Draft. Advice only. Counsel signs and sends nothing. Twelve-x stays anonymous. Decisions 1–3 are open and this
page is not a compliance record.**