# Counsel position — Gloomberb browser session cookie replayed from code

**Date:** 2026-10-05
**Author:** Counsel (`0e57e884-0920-4d5f-a17b-a94a98fb29d9`), on DIG-1206
**Responds to:** Security's [`POSITION-2026-10-05-session-cookie.md`](POSITION-2026-10-05-session-cookie.md) (DIG-1194), classification **Unclear**
**Terms read:** [`gloomber-terms-2026-10-05.txt`](gloomber-terms-2026-10-05.txt), effective 2026-09-26,
retrieved 2026-10-05T20:34:28Z from `https://gloom.sh/terms` (HTTP 200).
**Counterparty:** Cold Start Ventures Limited, Hong Kong.
**Forum if it ever comes to it:** §19 — Hong Kong law, HKIAC individual arbitration, seat Hong Kong,
one arbitrator, English, 30-day informal step via `hello@gloom.sh` first, class waiver.

| Artefact | sha256 |
|---|---|
| `gloomber-terms-2026-10-05.html` (byte-exact response) | `6f781a39c8a54ddd83eb1004a90e534dda77a6090d9f1bc5e418dcd3bffaa0fc` |
| `gloomber-terms-2026-10-05.txt` (text extract) | `0cd96156b00c81ad140aaa9aaa82ffcb84c3bcf29324c60112bd3b1966d1f265` |

Both hashes re-verified against the committed files on 2026-10-05. Security's index rows are correct.

**No vendor contact has been made and none is authorised by this issue.** This memo reads the terms
and the code. It does not sign, send, or decide anything.

---

## 1. Counsel's classification

Security's "Unclear" was the right call *as a security read*. Counsel's classification splits it,
because the terms give two different answers to two different access methods, and lumping them
together hides the useful part.

| # | Access method | Classification | Confidence |
|---|---|---|---|
| **A** | **Browser session cookie replayed against `api.gloom.sh`** (42 of 89 `digifetch_*` tools) | **Prohibited** on the current facts | **CONFIRMED** |
| **B** | **Anonymous reads, no credential** (47 tools) | **Unclear** — one open question only (§14), clean on everything else | **LIKELY** |
| **C** | **Properly scoped API key, on the current free non-team account** | **Prohibited** — same §14 gap as B, independent of transport | **CONFIRMED** |
| **D** | **API key or any interface, under a team plan or a written agreement from Cold Start** | **Permitted**, subject to §5 and §12 limits | **LIKELY** |

The single most important finding, and it is not the one Security flagged as most consequential:

> **We are not licensed to use this at all as an organisation, under any access method.** Buying an
> API key does not fix it. A team plan, or a written agreement, does.

That is why method A lands **prohibited** rather than unclear, and why methods B and C are also not
permitted today. Confidence on the §14 reading: **CONFIRMED** — it is a textual reading of an
unambiguous clause with a stated override, not a judgement call.

---

## 2. The five questions, answered

### Q1 — Is cookie replay "the interfaces and within the limits we offer for that purpose"? (§11 carve-out, T1)

**It does not matter how the first half of the carve-out resolves, because the second half fails.**

The carve-out is conjunctive: access is permitted only "**through the interfaces**" **and** "**within
the limits we offer for that purpose**". Security spent the analysis on the first conjunct and called
it the hinge. It is not the hinge, because the second conjunct fails on its own.

§12 defines the limits they offer for developer access:

> Use of the News API, our MCP server and other developer interfaces is subject to these Terms, our
> documentation and the limits of your plan. Keys are personal to you and must be kept secret. We may
> monitor usage, apply rate limits, and revoke or rotate keys that are exposed, abused or used in
> breach of these Terms.

A browser session cookie is none of those limits. It cannot be scoped to an integration, rate-limited
per integration, monitored as a key, or revoked without destroying a human's live session. The reason
a cookie fails is precisely the reason §12 says keys are used. So even if `api.gloom.sh` is conceded
to be "an interface we offer" — Security's Reading B — we are still **outside the limits**, and
outside the carve-out.

For completeness, on the first conjunct: **Reading A is stronger than Security gave it credit for.**
§3 enumerates "API keys, MCP connections and **device sign-ins**" as three distinct things. The
drafters knew the difference between a key and a browser sign-in and named both. We are using a
*device sign-in* credential as though it were an *API key*. That is not a technicality; it is the
distinction the term itself draws.

Classification of method A on the §11 limb: **prohibited. CONFIRMED** (on the second conjunct; on the
first conjunct, LIKELY against us).

**Correction to Security's framing, in Security's favour and against Security:** it is not true that
this is "arguably both ways". The contestable question Security identified is one the answer does not
depend on. That is a better position, not a worse one — we do not have to win the argument.

### Q2 — Are we licensed at all as an organisation? (§14, T3)

**Confirmed against us. This is the load-bearing finding, and it is worse than Security framed it.**

§14:

> we grant you a limited, revocable, non-exclusive, non-transferable license to access and use the
> Services for your personal use or, **under a team plan**, for the internal use of your organization.

The grant has two limbs. Personal use is unconditional. **Organizational internal use is conditioned
on a team plan.** We are an organisation, we use this internally, and we hold a free account with no
team plan. So the only limb available to us is "your personal use" — and digithings is not a person.

§5 does not rescue it. §5 ("data and content you receive through the Services are for your own
personal or internal use") is a **cap on redistribution, not a grant of access** — Security's reading
is correct. It tells you what you may do with data you have received. It does not give you a right to
receive it. The affirmative grant is §14, and §14 is conditioned.

The counter-argument, and why it does not win: the preamble expressly contemplates organisational use
("If you use the Services on behalf of an organization, you agree to these Terms for that
organization"). But that clause is about **who is bound**, not about **what is granted**. It tells you
the organisation accepts the Terms; it does not give the organisation a licence that §14 withholds
from organisations without a team plan.

**This applies to every access method.** A properly scoped API key does not cure it. Method C is
prohibited for the same reason method A is. Security is right, and this is the finding that should
drive the CTO conversation.

**Two cures, and one of them is not money.** §21:

> If an order form or written agreement conflicts with these Terms, it prevails for the Services it
> covers.

and §8: "Team plans may be subject to an order form or separate written agreement." So:

1. **Buy a team plan.** Costs money at checkout, price not published on the terms page. Chris's call.
2. **Get a written agreement from Cold Start** granting organisational internal use. Also §21, and it
   is the *only* route that could additionally authorise a credential we control, because no plan tier
   automatically converts a browser session cookie into "an interface we offer".

Cure 2 is strictly more useful and is not obviously more expensive. It needs one authorised vendor
contact, which this issue does not grant. See question 3 for Chris.

### Q3 — Does the data-delay control bite? (§5 delay, §11 second limb, T2)

**No. Security's delay concern is correctly identified and then over-weighted.**

§11 prohibits "bypass or **interfere with** authentication, rate limits, usage limits, plan
restrictions, data delays or other access controls". The verb is *interfere with*. Interference
requires doing something to the control — obtaining fresher data than the plan allows, or replaying a
credential that carries a paid entitlement.

If the account is on a free plan, the delay **is** the offered limit, and consuming delayed data is
consuming it inside the limit. There is nothing to interfere with. Our client already enforces the
adjacent plan restriction correctly: pro-only tools answer `pro_required` for a valid free session
rather than returning premium data (`client.py:1280`; documented in the runbook).

So the delay limb of §11 **does not bite. CONFIRMED**, subject to the free-plan fact.

**And this is the second correction to Security's framing:** the delay question is **not** what
separates a documentation defect from a live breach. Security wrote that it "must be answered before
any production read". It need not be answered before any production read *for legal reasons* — the
classification does not move. It is still worth confirming as an **operational and financial**
matter, for a reason Security did not have: §8 says free trials "**require a payment method**" and
"unless you cancel before the trial ends, your subscription starts and you will be charged when the
trial ends". So there is a live question whether anyone ever put a card on this account and whether a
trial silently converted. That is a money question for Chris, not a legal-classification question,
and it is folded into question 2 below rather than raised as a separate card.

**Ongoing discipline, not a one-time gate:** if the plan ever changes, the delay analysis has to be
redone. Do not carry a free-plan conclusion across a plan change.

### Q4 — Does publication create exposure independent of use, and do we create counter-exposure?

**Publication: real exposure, materially weaker than the PrimeMarket publication I found in
DIG-461, and I must not carry that reasoning over.**

On PrimeMarket, §12 said "Any unauthorized extraction or use of platform data constitutes a **material
breach**" — publication of the recipe was part of the unauthorised use, and the vendor had pre-labelled
it. **Gloomberb has no equivalent escalation clause.** Nothing in §11 or §12 prohibits *describing*
how to obtain a credential. §11 is a list of prohibited conduct; §12 sets interface limits. A
documented recipe is not itself conduct.

There is one hook, and it is the right one to name because it is the vendor's own words. §11 opens:

> You agree not to, and **not to help anyone else to**: scrape, crawl or bulk download data from the
> Services … ; bypass or interfere with authentication …

Publishing a step-by-step recipe for extracting a session credential is, on its face, assistance to
others to obtain a credential that bypasses the offered authentication model. That engages the "help
anyone else" limb. **But it is arguable, not express** — a reader who follows our recipe still needs
their own valid account, and we are not defeating authentication for them.

Classification: publication is an **arguable** breach of the §11 "help anyone else" limb, and
**UNSURE** as a standalone breach. Security's removal was right on the §3 and reputational grounds
regardless — see below.

**There is a cleaner, non-terms reason the exposure mattered, and it should drive the remediation:**
§3 — "Keep your password and keys confidential, do not share your account with others". We published
the *method*, not a value, so there is no §3 breach in the publication itself. But a public method
plus a live credential on a developer machine is a combination we should not leave standing, and that
is a §3 exposure created by *our own conduct*, not by the vendor's terms.

**Counter-exposure from publishing their terms and our analysis: low. Publishing the archive is the
safer posture, not the riskier one.**

- The terms are a public legal document served at a public URL. Reproducing a public document for
  legal-compliance analysis, with source, timestamp and hash, is the paradigmatic fair-dealing case.
- I found **no clause** in the terms that imposes any confidentiality obligation over the terms text
  itself, and no clause prohibiting description of the terms.
- §2's brand clause is a **non-grant**, not a prohibition: the MIT licence "does not grant any right
  to use the Gloom or Gloomberb names … except as needed to describe the origin of the software
  accurately". Naming whose terms we archived is neither origin-describing nor misleading.
- Our own `docs/VENDOR_CONTENT_BOUNDARY.md` step 2 **requires** the artefact to be committed. Complying
  with our own policy is the defensible position.

Risk if I am wrong: a trademark non-grant is not a cause of action on its own, and a non-compliant
copy of a public ToS supports at most a takedown request. **LIKELY low. No action required.**

**The trademark note** Security raised out of scope: I would go further than "low severity".
Using "Gloomberb" as a data-source label *is* descriptive reference — it says whose data this is — and
is arguably inside the §2 carve-out rather than outside it. It is not an origin description, but it
is also not a claim of origin, endorsement, or affiliation. **No prohibited conduct. Defer to the
repo-wide trademark pass** (`task/1132-license-trademark-fix`). Do not block this PR on it.

### Q5 — Remediation order, and must the account be closed?

**Security is right that the credential must be destroyed rather than rotated, and right that the
method survives in git history. The order needs one correction, and there is a split Security's
plan does not make.**

**The 42 gated tools and the 47 anonymous tools are not one problem.** Method A is prohibited.
Method B is unclear on a single question. Deleting or freezing the entire `digifetch/gloomberb`
family is over-remedy: it removes the 47 tools whose only open question is §14 and which a team plan
would cure. **Correct order:**

1. **`GLOOMBERB_ENABLED` off in deployed environments. First, today, by anyone.** Needs no
   credential and no account session. It is the only step that can happen today, so it goes first.
   Default-ON is the wrong default for a prohibited method; Security is right on this and it should be
   a code change on the digifetch family, owned outside this issue.
2. **Destroy the credential everywhere.** Local `.env`; the GitHub Actions `cron` environment secret —
   *deleted*, not overwritten; and any CI log or shell history that captured a value. Requires a
   Gloomber account session. Owner: Security. Blocked on `dt-login` and Bitwarden (DIG-95). Recorded
   as a recommendation with a named owner, not as done.
3. **Close the account. After step 2, and note why the order matters.** Closing the account is the only
   action that revokes the session **server-side**. Destroying our copy leaves the cookie live in
   Cold Start's session store until it expires. Destroy-then-close; if only one is possible, close.
   **This step also needs a Chris answer** — see question 2, because §15 says deleting "cancels any
   active subscription immediately, and the remaining period is not refunded", and §9 makes
   non-refundability express including for "accounts that are deleted". If a trial converted under §8,
   closing the account destroys money. Check the billing state before clicking delete.
4. **Leave the client code, gated.** Do not delete `digifetch/gloomberb` in this pass. Deleting a
   working client is a larger change than the current risk justifies, it discards the anonymous half,
   and step 1 already removes reachability. Revisit once the §14 question is answered either way.

**Must the account be closed? Yes — Counsel's recommendation.** Not for tidiness:

- It is the only step that actually revokes the credential server-side.
- §15 lets Cold Start suspend or terminate "if your use creates risk or possible legal exposure for us
  or others". An account we are using under a licence we do not hold is a standing invitation, and a
  suspended account is a worse outcome for us than a closed one.
- Closing the account ends method A and the §14 exposure for the credentialed path completely.
- It creates no vendor-relationship cost: we have no paid plan, no written agreement, and no history
  with Cold Start that we would be giving up.

**Closing the account does not fix the 47 anonymous tools.** Those need no account. They are governed
by §14, and only a team plan or written agreement answers §14.

**Git history: do not rewrite. Counsel's decision, recorded with reasons.**

The recipe was public from **2026-09-16** (commit `9ac0eea84`, merged to `develop`, so published) to
**2026-10-05**. A history rewrite on a public repository does not achieve confidentiality: forks,
clones, CI caches and anyone who read it in those 19 days retain the content, and our own boundary
document says "GitHub does not truly delete history". The cost is high — it destroys the audit trail
that our whole change-traces-to-an-issue discipline depends on — and in a dispute it would look like
evidence destruction to a Hong Kong arbitrator while we hold the §18 indemnity. The benefit is
approximately zero against a 19-day exposure.

What should happen instead, and does: the redaction commit stands, and **this memo records the
window, the choice, and the reasons**, so the decision is auditable rather than invisible.

**Systemic fix, for the record:** do not publish an acquisition method for any vendor surface before
that vendor's terms have been read. That is the whole failure mode here and on PrimeMarket, and
`docs/VENDOR_CONTENT_BOUNDARY.md` already encodes the rule.

---

## 3. What this costs, honestly

§17 caps Cold Start's liability at the greater of fees paid in 12 months or US$100. On a free account
that is **US$100**. That cap protects *them*, not us.

**The real financial exposure runs the other way, through §18:**

> you will indemnify and hold harmless Cold Start and its directors, officers, employees and
> contractors from any claims, losses, liabilities and expenses, including reasonable legal fees,
> arising out of Your Content, **your use of the Services in breach of these Terms**, or your
> violation of any law or third-party right.

The indemnity is not capped by §17 — §17 limits *their* liability. So the exposure shape is: a claim
in Hong Kong under HKIAC rules, one arbitrator, English, with our own indemnity to Cold Start and a
US$100 cap on what they owe us. **UNSURE** whether a successful claim is realistic on these facts — no
demand has been made, no contact has been made, and our use has been dormant. But the *shape* is
asymmetric and unfavourable, and it is the reason the cheap cure (a team plan) is worth taking.

**It has not been incurred yet.** No contact, no demand, no automated production read, and the code
path fails closed with zero HTTP requests when no credential is present. The mitigation work already
done (method removed from public docs, cookie never logged, never sent cross-origin, cached by
truncated hash) is genuinely good and should be credited.

---

## 4. Questions for Chris

Numbered, in the order they block work. Only Chris can decide these: two commit money or authorise a
vendor conversation, one is irreversible.

1. **Authorise one written contact to Cold Start (`hello@gloom.sh`), or not?** Every clean path needs
   it — a scoped API key, a team plan, or a written agreement under §21. Security has made no contact
   and this issue does not authorise one. Counsel cannot initiate it: it commits the company to a
   negotiation and may disclose our position. **Recommended: yes, authorise a short factual enquiry
   about team plans and API access, with no admission and no reference to the cookie method.**
   If no, the default is method D is unavailable and methods A–C stay non-permitted.

2. **Is there a payment method on the Gloomberb account, and did a trial convert?** §8: free trials
   "require a payment method" and auto-convert to a paid subscription at trial end. §15: deleting the
   account "cancels any active subscription immediately, and the remaining period is not refunded".
   §9 makes non-refundability express. **So closing the account — which Counsel recommends — could
   destroy money if a trial converted.** This must be checked before the account is closed, and it is
   why the close step is sequenced after a billing check rather than done blind. Overlaps the
   subscription fact Security already put to Chris; please answer both together.

3. **If a team plan is the route: approve the spend, or route it to the Tax Specialist first?**
   Price is not published on the terms page and shows only at checkout, so I cannot bound it. A
   recurring vendor subscription is an operating expense rather than revenue, which suggests the
   forfettario 85,000 EUR revenue limit is not engaged — but that is the Tax Specialist's call to make
   and record, not mine. **Recommended: let Security get the checkout price, Tax Specialist confirm
   treatment, then decide.** A written agreement under §21 may be cheaper and strictly more useful,
   which is why question 1 asks for both options in the same message.

---

## 5. Sign-off on PR #5157

**Approved, on the state described below.**

`docs/VENDOR_CONTENT_BOUNDARY.md` step 5 requires Counsel's written sign-off before a PR touching a
vendor merges to a public repository. This is it. It is **conditional on two one-line corrections**,
both inside this PR's own diff, both made in the same commit as this memo. Had they not been made, this
would have been a block with these two specific required changes:

1. `docs/ops/gloomberb-session-cookie.md:21` reads "**UNCLER**" in the compliance-status banner. That
   is a typo, and it sits in the one line a reader will quote — in a PR whose entire purpose is to
   make the compliance record accurate. Corrected to `UNCLEAR`, then to the final classification.
2. The same banner said "Counsel sign-off pending" with no memo reference. Corrected to name this
   memo, the date, and the per-method classification, so a reader of the runbook lands on the
   position rather than on a stale status.

**What I checked and approve, without reservation:**

- The acquisition method is removed from both public documents, and **the client contract is kept**.
  That is the right line: what the client accepts is a fact about our own code; how to obtain a
  credential is the part with exposure.
- The runbook keeps the design rationale, the tool inventory and its own provenance, and adds a
  redaction note explaining what was removed and why. Good practice, and it is why history is not
  being rewritten.
- The corrected `client.py:403-407` citation, with the note that the old `client.py:180-183` citation
  was wrong and had propagated into DIG-1194. Corrections of this kind are exactly what the boundary
  discipline exists to produce.

**No objection to the code path remaining in the repo.** Gating method A is step 1 above; deleting
the client is step 4 and is deliberately deferred, with reasons, rather than smuggled into a docs PR.

**Scope of this sign-off.** It approves this PR — a reduction in exposure plus a compliance record —
and it approves **no new Gloomber access work**. Methods A, B and C remain non-permitted until
question 1 or a team plan resolves §14. If anyone proposes a cookie-gated read reaching a hosted or
end-user surface, §5 and §12 both prohibit it and this memo does not cover that case: §12 permits
building applications "for yourself **or for users who have their own access**", so a hosted digichat
surface is permitted only where the end user holds their own Gloomberb access. That is the tripwire,
and it needs a fresh Security and Counsel review, not an extension of this memo.

---

## 6. Confidence summary

| Finding | Confidence | What would change it |
|---|---|---|
| §14 does not license our organisational internal use on a free non-team account | **CONFIRMED** | A written agreement or order form under §21, or a team plan |
| Cookie replay is outside the §11 carve-out (second conjunct, "within the limits we offer") | **CONFIRMED** | A written agreement naming the credential |
| Cookie replay is outside the carve-out on the first conjunct too ("the interfaces") | **LIKELY** | Vendor documentation offering session-cookie access as a developer interface |
| Delay control (§11) does not bite on a free plan | **CONFIRMED** | Evidence the account is on a paid real-time plan nobody paid for |
| Publication is an arguable §11 "help anyone else" breach, not an express one | **UNSURE** | A demand from Cold Start; a ruling on assist-the-breach under HK law |
| Publishing the terms archive creates negligible counter-exposure | **LIKELY** | A trademark claim (low value — §2 is a non-grant, not a prohibition) |
| No rewrite of git history is the right call | **LIKELY** | A formal legal demand requiring preservation |
| §18 indemnity is the real exposure, not §17's US$100 cap | **LIKELY** | An actual claim, which would let me read Cold Start's real position |

**What I could not determine, and will not guess:** whether the account is free or on a converted
trial (question 2); the price of a team plan; whether Cold Start would grant a written agreement. The
first is checkable in an account session. The second appears only at checkout. The third requires the
contact that question 1 asks Chris to authorise.

**What would change my mind on the headline classification:** a written agreement from Cold Start that
either grants organisational internal use (§14 cured) or names the session credential as an offered
interface (§11 cured). Either one moves method A from **prohibited** to **permitted**. Nothing in
Gloom's published terms, on their own, cures either.

---

## 7. Related records

- Security's read: [`POSITION-2026-10-05-session-cookie.md`](POSITION-2026-10-05-session-cookie.md) (DIG-1194) — Unclear
- Index entry, updated with this memo: [`INDEX.md`](INDEX.md)
- Boundary policy: `docs/VENDOR_CONTENT_BOUNDARY.md` (OSS Researcher, DIG-503) — step 5 required this memo
- Prior precedent on publication, **not** portable: DIG-461 / DIG-503 (Prime Terminal, §12 material-breach clause)
- Source issue: DIG-1194 · This memo: DIG-1206