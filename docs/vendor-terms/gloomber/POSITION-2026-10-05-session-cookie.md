# Gloomberb position — browser session cookie replayed from code

**Date:** 2026-10-05
**Author:** Security (`b14d7a18-99b9-4c04-899b-efdd4676cfd0`), on DIG-1194
**Classification:** **Unclear** — escalate to Counsel
**Terms read:** [`gloomber-terms-2026-10-05.txt`](gloomber-terms-2026-10-05.txt), effective 2026-09-26,
retrieved 2026-10-05T20:34:28Z from `https://gloom.sh/terms`.

This is Security's reading of the terms, not a legal opinion. Counsel owns the opinion.

---

## 1. The question

We take the session cookie from a logged-in Gloomberb browser session, copy it out of browser
storage, and replay it from our code as the credential for `https://api.gloom.sh`. That is the
pattern published at `docs/ops/gloomberb-session-cookie.md`, described end to end in
`docs/superpowers/plans/2026-09-16-gloomberb-session-cookie-runbook.md`, and implemented in
`digiquant/src/digiquant/data/gloomberb/client.py` (cookie names pinned at `client.py:405-406`).

Do Gloom's terms permit it?

## 2. What we actually do, verified

Every claim below was checked against `github/develop` at `713e58b8f` on 2026-10-05.

- 89 `digifetch_*` tools exist; 42 are cookie-gated (41 `GLOOMBERB_SESSION_COOKIE`, 1
  `SUBSTACK_SESSION_COOKIE`); 47 work without a cookie.
- The cookie is obtained from a human's logged-in browser at the vendor's own terminal, by the
  operator's own sign-in. It is not issued to us by Gloom.
- **No workflow in the repository sets any `GLOOMBERB_*` variable.** `git grep GLOOMBER --
  .github/workflows/` returns empty. The runbook names the GitHub Actions `cron` environment secret
  as the canonical production store, but no workflow file references it. We cannot enumerate GitHub
  secrets — they are write-only — so the honest claim is "unreferenced in the repo as of
  `713e58b8f`", not "does not exist".
- The client fails closed: with no cookie it returns a typed `auth_required` and makes **zero** HTTP
  requests. `GLOOMBERB_ENABLED` is the family kill switch and defaults to on; any other value
  disables the family.
- The cookie is never logged, is never sent across a cross-origin redirect hop, and only ever keys
  a cache by a truncated SHA-256 fingerprint.
- A live cookie is present in one developer machine's `.env` (name verified, value not read).
- We do not resell Gloomberb data and do not publish it. We published the **method**.
- `mcp.digithings.ai` is commented out and human-gated
  (`apps/digithings-stack-cloudflare/wrangler.toml:69,77,104`).

Net exposure today: **the method is public, one credential is local, and the automated path is
dormant.** That is materially smaller than "we scrape a vendor in production", and it should be
stated plainly rather than inflated. It is not zero, and it is not durable — the credential exists
and the code path is one environment variable away from running.

## 3. The clauses that decide it

Quoted verbatim from the archived artefact.

**§5, Market data and third-party content** — the permission, and its limits:

> Unless your plan or a written agreement with us says otherwise, data and content you receive
> through the Services are for your own personal or internal use. You may not resell, redistribute,
> publicly display or make them available to others as a data feed or in a competing product.

and, two sentences earlier:

> Free plans receive delayed data, and real-time availability depends on your plan and on our
> providers.

**§11, Acceptable use** — the prohibitions, and the only carve-out in the whole document:

> scrape, crawl or bulk download data from the Services, or use the Services to build a competing
> product or dataset, **except through the interfaces and within the limits we offer for that
> purpose**;

> **bypass or interfere with authentication, rate limits, usage limits, plan restrictions, data
> delays or other access controls**;

**§12, APIs, MCP and keys** — what "the interfaces we offer" actually are:

> Use of the News API, our MCP server and other developer interfaces is subject to these Terms, our
> documentation and the limits of your plan. Keys are personal to you and must be kept secret.

> You may build applications that use our interfaces for yourself or for users who have their own
> access, but you may not offer our data or interfaces as a standalone feed or service to third
> parties without our written permission.

**§14, Our intellectual property** — the licence grant:

> we grant you a limited, revocable, non-exclusive, non-transferable license to access and use the
> Services for your personal use or, **under a team plan**, for the internal use of your
> organization.

**§2, Open-source software** — the defence that does not work:

> The Gloomberb source code is published under the MIT License. […] These Terms govern the hosted
> Services, our accounts and APIs, **the data and content we provide**, and the builds we
> distribute.

**§3, Eligibility and accounts:**

> You are responsible for all activity under your account, API keys, MCP connections and device
> sign-ins.

**§15, §18, §19** — consequence, exposure, forum. Cold Start may suspend or terminate for breach
(§15). **We** indemnify them for "your use of the Services in breach of these Terms" (§18) — so the
real financial risk is our indemnity, not their liability cap. Disputes go to Hong Kong law and
HKIAC individual arbitration, with a 30-day informal-resolution step that requires contacting
`hello@gloom.sh` first (§19). No vendor contact has been made and none is authorised by this issue.

## 4. The five tests

**T1 — Is a replayed browser session cookie "the interfaces we offer"?**
This is the hinge of the whole question, and it does not resolve cleanly. §11's carve-out only
protects access "through the interfaces and within the limits we offer for that purpose", and §12
names what those interfaces are: the News API, the MCP server, "other developer interfaces", and
keys. Gloom *does* offer an `api.gloom.sh` surface that requires a session — so the endpoint is one
of theirs. But every interface Gloom describes in §12 carries a **key**, and keys are issued,
revocable, scoped and auditable. A session cookie taken out of a browser is none of those things:
it cannot be scoped, it cannot be rate-limited per integration, it cannot be revoked without
killing the human's session, and Gloom never consented to it being used this way. Security's read:
**arguably outside the carve-out, but arguable the other way**, because the vendor does offer a
session-gated API. Unclear.

**T2 — Do we bypass authentication or a data delay?**
This is where I was wrong in my first pass, and it is worth being explicit. We are **not**
bypassing authentication. We authenticate with our own valid account credentials — there is no
defeated login, no forged token, no credential stuffing. §11's authentication limb does not bite on
that basis.

The delay limb is different and depends on a fact we do not have: §5 says free plans receive
delayed data. If our account is on a free plan and the gated reads arrive on a delayed schedule,
we are inside the plan's limits. If the account is on a paid real-time plan that nobody has paid
for, or if we are pulling real-time data on a free plan, we are interfering with a data delay —
which §11 names expressly. **This is a factual question only the account owner can answer**, and it
goes to Chris because it is a subscription question. It must be answered before any production read.

**T3 — Are we licensed at all, as a company?**
§5 permits "your own personal or internal use". §14 grants the licence "for your personal use or,
**under a team plan**, for the internal use of your organization". digithings is an organization
using this internally, not a person using it personally, and the runbook records a free account with
no team plan and no written agreement. Reading §5 and §14 together, **our organisational internal use
is not clearly licensed at all** — §5 reads as a cap on redistribution rather than an affirmative
grant, and §14's affirmative grant for organisational use is conditioned on a team plan we do not
have. This is, in Security's view, the single most consequential ambiguity in the document, and it
would apply to any access method — key-based, cookie-based, or anything else — not just this one.
Unclear, and materially against us.

**T4 — Do we redistribute, or build a competing product?**
Clean. §5 and §12 both prohibit reselling, redistributing, publicly displaying, or offering data as
a standalone feed. We do none of those. digichat is a hosted product, so the *next* question matters:
if any external user can cause a cookie-gated Gloomberb read to be returned to them, that is
"make them available to others". Today the gated tools are internal and `mcp.digithings.ai` is
human-gated and commented out. **Permitted as things stand, with a live tripwire**: if a gated read
ever becomes reachable from a hosted surface, this flips to prohibited. The `GLOOMBERB_ENABLED`
kill switch is the control that holds that line and it currently defaults to on, which is the wrong
default for this risk.

**T5 — Does the app's MIT licence save us?**
No, and this is worth closing off explicitly because it is the argument someone will reach for. §2
puts the MIT licence on the **source code** and states in the same breath that the Terms "govern
the hosted Services, our accounts and APIs, the data and content we provide". Open-sourcing the
terminal does not license the terminal's data or our right to a hosted session. Security's read:
**the MIT defence fails.**

## 5. Classification

**Unclear.** Not "permitted" — the carve-out in §11 is narrow, the §14 licence gap is real, and two
of the five tests land against us. Not "prohibited" either — Gloom offers a session-gated API
surface, we authenticate with our own account, we bypass nothing, we redistribute nothing, and the
automated path is currently dormant. A classification of "prohibited" would need Counsel to read
§11's carve-out against us and §14's team-plan condition against us, and I am not going to
pre-empt a legal opinion from a security read.

Under boundary checklist step 5, **Unclear and Prohibited both mean: escalate to Counsel and
Security, and do not merge.** Security is the escalation here. Counsel sign-off is required in
writing before any new Gloomber access work merges to a public repo.

There is a strong plausible-prohibited reading — T1, T3 and T5 together — so Counsel should be
briefed on the assumption that this may land prohibited, and the operational cost of being wrong
should be understood: an account suspension (we have a free plan, so the cost is the data, not the
subscription) plus an §18 indemnity claim.

## 6. What Security decides now, without waiting for Counsel

None of the following needs a legal opinion, and none of it is a vendor contact.

- **No new Gloomber access work merges to a public repo** until Counsel signs off. `GLOOMBERB_ENABLED`
  stays as the kill switch.
- **The published method stops being public.** The acquisition steps leave `docs/ops/` in this
  repository. The capability stays — an operator who holds a session can still drive the client —
  but the repo stops publishing how to obtain one. This is the same decision, for the same reasons,
  as the PrimeMarket session-acquisition recipe removed in DIG-503.
- **Answer T2 before any production read.** The account's plan must be confirmed by Chris. Until it
  is, Security treats production volume as off the table regardless of what Counsel concludes,
  because a delay-gate question is a fact question and we do not have the fact.
- **T4 holds as a tripwire.** No gated Gloomberb read may become reachable from a hosted or
  end-user-facing surface without a fresh Security and Counsel review. I am recommending that
  `GLOOMBERB_ENABLED` default to off in deployed environments; that is a code change for whoever
  owns the digifetch family, not something this issue changes.
- **The local credential should be destroyed, not rotated.** A session cookie is not rotatable —
  rotation means re-acquiring it, which is the same prohibited method. The correct end state is no
  cookie on any machine, and `GLOOMBERB_ENABLED` off. I cannot do this myself this run: revocation
  needs a Gloomberb account session, and our dashboard-login path (`dt-login`) is not installed on
  this Mac and Bitwarden is not yet bootstrapped (DIG-95). Recorded as a recommendation with a
  named owner rather than done and overclaimed.

## 7. Questions for Counsel

Framed so that Counsel does not have to re-derive any of our facts. Each is a legal question, not
an engineering one.

1. §11's carve-out — "through the interfaces and within the limits we offer for that purpose" —
   does a browser session cookie against `api.gloom.sh` qualify as "the interfaces we offer", given
   that §12 describes every developer interface as key-based and revocable?
2. §14 conditions organisational internal use on a team plan. On a free plan with no written
   agreement, is digithings licensed to use the Services internally at all — by any method?
3. §5's "your own personal or internal use" is qualified by "unless your plan or a written
   agreement says otherwise". Does a free plan's terms say otherwise about internal use by a
   company?
4. If the answer to 1 or 2 is no, does the exposure run to §18's indemnity, §19 arbitration in Hong
   Kong, or both — and does the dormant state (credential local, no CI reference, no redistribution)
   change either?
5. §11 names "data delays" as an access control. If our account is on a delayed free plan, is
   consuming delayed data through a session-gated endpoint "within the limits we offer", or does the
   endpoint choice itself put it outside?

## 8. One finding outside this issue's scope, recorded not acted on

§2 states that the MIT Licence "does not grant any right to use the Gloom or Gloomberb names, logos
or other brand features, except as needed to describe the origin of the software accurately". Our
public repository uses "Gloomberb" as a data-source label in docs and code, which is not describing
the origin of the software — we are not a Gloomberb derivative. Severity is low: no conduct is
prohibited, and a descriptive reference to a vendor is ordinary. But it is a brand-licence term in
the same document, in a public repo, and it should be in the record. It is **not** acted on here
because it collides with the repo-wide trademark work already in flight (`task/1132-license-trademark-fix`)
and because this issue's scope is terms compliance, not naming. Flagged to the CTO.
