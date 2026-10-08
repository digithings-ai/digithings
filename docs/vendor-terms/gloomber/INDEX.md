# Vendor terms index — Gloomberb

Boundary: `docs/VENDOR_CONTENT_BOUNDARY.md` (OSS Researcher, DIG-503).

Every entry answers boundary checklist step 6: vendor, access method, classification, artefact
hash, decision date, decider, Counsel memo reference.

---

## Browser session cookie replayed against the Gloom Cloud API

| Field | Value |
|-------|-------|
| Vendor | Gloomberb / Gloom — operated by Cold Start Ventures Limited (Hong Kong) |
| Access method | A logged-in browser's session cookie, copied out of browser storage and replayed as a credential from code against `https://api.gloom.sh`. Not the News API, not the MCP server, not an issued key. |
| Terms URL | `https://gloom.sh/terms` (HTTP 200) |
| Retrieved | 2026-10-05T20:34:28Z |
| Terms effective | 2026-09-26 |
| Artefact (HTML) | `docs/vendor-terms/gloomber/gloomber-terms-2026-10-05.html` |
| sha256 (HTML) | `6f781a39c8a54ddd83eb1004a90e534dda77a6090d9f1bc5e418dcd3bffaa0fc` |
| Artefact (text extract) | `docs/vendor-terms/gloomber/gloomber-terms-2026-10-05.txt` |
| sha256 (text) | `0cd96156b00c81ad140aaa9aaa82ffcb84c3bcf29324c60112bd3b1966d1f265` |
| Relevant clauses | §2 (open-source licence covers code, not data), §3 (account owner liable for all activity, keys and sign-ins), §5 (free plans get delayed data; data for "personal or internal use" only; no redistribution or competing product), §11 (no scraping, no bypassing authentication or data delays, except "through the interfaces and within the limits we offer for that purpose"), §12 (developer interfaces subject to the terms and plan limits; no standalone feed to third parties without written permission), §14 (licence is for "personal use or, under a team plan, for the internal use of your organization"), §15 (suspension for breach), §18 (we indemnify them for use in breach), §19 (Hong Kong law, HKIAC arbitration) |
| Classification (Security, DIG-1194) | **Unclear** — escalate to Counsel (boundary step 5) |
| Position record | [`POSITION-2026-10-05-session-cookie.md`](POSITION-2026-10-05-session-cookie.md) |
| **Classification (Counsel, 2026-10-05)** | **PROHIBITED** for browser session cookie replay. **PROHIBITED** for any method while §14 is unmet (incl. a scoped API key). **Permitted** under a team plan or written agreement (§21). |
| Decision date | 2026-10-05 |
| Decider (first pass) | Security (`b14d7a18-99b9-4c04-899b-efdd4676cfd0`), on DIG-1194 |
| Decider (final) | Counsel (`0e57e884-0920-4d5f-a17b-a94a98fb29d9`), on DIG-1206 |
| Counsel memo | [`COUNSEL-2026-10-05-session-cookie-position.md`](COUNSEL-2026-10-05-session-cookie-position.md) — Counsel opinion, per-method classification, remediation order, 3 questions for Chris. **Counsel sign-off on PR #5157: approved** (boundary step 5 satisfied). |
| Operational effect | `GLOOMBERB_ENABLED` must default **off** in deployed environments — Counsel's step 1, doable now without a credential. Credential must be **destroyed, not rotated**, then the account closed (deletion revokes the session server-side). Check the account's billing state first: §8 auto-converts trials, §15/§9 make deletion non-refundable. Client code stays, gated. |

---

## Why this entry exists

Counsel flagged in DIG-503 that this is the same pattern as PrimeMarket with a second vendor, and
declined to guess at what Gloom's terms allow. Nobody had read them. They are 3,072 words long,
served from a live URL, and take eleven minutes to read. That is the whole failure mode: not a
missing legal opinion, a missing document.

## Security decision record — 2026-10-05, after Counsel's memo

Security's own answers in DIG-1194 were given before Counsel's memo was read, and one of them is now
in tension with it. Both facts belong in this index, because this index is the record that is checked
before anyone relies on this entry.

**Chronology, all 2026-10-05 UTC.** Security classified Unclear at ~20:40 and asked Chris three
questions. Counsel's prohibiting memo and PR #5157 sign-off were committed at 21:16 and 21:18.
Chris answered Security's card at 21:38 — after those commits, but whether he had read the memo is not
known, and Security does not assume either way.

**What Chris answered.**

| Question | Answer |
|---|---|
| Plan on the account | `free`. This closed Security's open delay question: §5 delays free-plan data, and §11 names delays as an access control, so a free plan sits inside the offered limits. |
| Team plan or written agreement | **No team plan.** (His comment was about Bloomberg, a different vendor. His design principle — the end user brings their own vendor account — is not an answer about Gloom and is not recorded here as one.) |
| Path for the cookie | Keep using it while it is functional, and move it into Bitwarden so it is not hard-coded. |

**The tension.** Security recommended destroying the credential and not rotating it. Counsel then ruled
method A prohibited with CONFIRMED confidence. "Keep it while functional" cannot coexist with a
confirmed prohibition without being a deliberate acceptance of a prohibited use, so Security did not
act on it either way and put the decision to Chris a second time, with Counsel's ruling stated.

**Corrections Security accepts from Counsel's memo.** Two, both of which make our position stronger:

1. The §11 carve-out is conjunctive — "through the interfaces **and** within the limits we offer".
   Security treated the first conjunct as the contested one. The second fails independently: a
   browser session cookie cannot be scoped per integration, rate-limited per integration, monitored
   as a key, or revoked without killing a human's live session, which is why §12 specifies keys. We
   do not need to win the contested argument.
2. The billing fact is a money question, not a classification question. It does not move the
   classification, and Security should not present it as if it did.

**One earlier Security claim is superseded.** DIG-1194 treated the 47 credential-free tools as clean.
Counsel classifies them as **Unclear** on the same §14 question. Destroying the cookie does not fix
them, and closing the account does not fix them.

**What Security has not done.** No contact with Cold Start. No credential destroyed. Nothing moved
into Bitwarden. `GLOOMBERB_ENABLED` not changed — that is a code change owned by the digifetch tree.
No rotation: a session cookie is not rotatable, and "rotation" here means re-running the very
acquisition method that was removed from the public docs.

**Live trackers.**

| What | Where |
|---|---|
| Prohibited-pattern remediation ladder, owners named | DIG-1232 (critical) |
| Code containment: `GLOOMBERB_ENABLED` default off | DIG-1233 (critical) |
| Counsel's classification and remediation order | [`COUNSEL-2026-10-05-session-cookie-position.md`](COUNSEL-2026-10-05-session-cookie-position.md), DIG-1206 (done) |
| Security's original read, kept for provenance | [`POSITION-2026-10-05-session-cookie.md`](POSITION-2026-10-05-session-cookie.md) |
| Publication decision for `docs/ops/SECRETS_INVENTORY.md` | `docs/ops/SECRETS_INVENTORY.md`, section "Vendor terms and what this file may publish" |

---

## Accepted use — 2026-10-06

Appended 2026-10-06 by Security. Nothing above this line is edited by it.

Chris was shown Counsel's **Prohibited, confirmed** memo and answered four questions
on DIG-1194. His answers, in the order asked:

| Question | Answer |
|---|---|
| The 42 cookie-gated tools | **keep them running** — *"our tools don't have clients yet, I'm just experimenting with the cookie method. I won't publish yet."* |
| Custody of the cookie | **move it to Bitwarden** |
| Contact with `hello@gloom.sh` | **not authorised** — his reply was a strategy note about other vendors, not permission for Cold Start |
| Payment method on the account | **none** |

**What this entry now says.** A prohibited access method is in deliberate use, accepted
by the decision owner on 2026-10-06 with the finding in front of him. The acceptance is
**of an internal experiment only**. It lapses if anything about the method is published,
if a hosted or client-facing surface can reach the gated tools, if the plan changes, if
the account is closed, or if Counsel's position changes. §12 is the reason the second
tripwire exists: it permits apps "for yourself **or for users who have their own
access**", which is not the same permission as our own experiment.

**Three facts this entry would otherwise get wrong, so they are corrected here.**

1. **No money is at stake.** No payment method is on the account, so §8 cannot have
   auto-converted a trial and §15/§9 deletion refunds nothing because nothing was
   charged. Counsel's billing question is answered; account deletion is money-safe
   whenever Chris wants it, and is not authorised only because "keep it running" keeps
   the account.
2. **The credential still has no home.** Chris authorised the Bitwarden move; it is
   blocked. The `keymaster` machine account authenticates, `bws project list` returns
   nothing, and `bws project create` is refused with *"maximum number of projects (3)
   for this plan"* — quota exhausted, no grant on any existing project. Granting that
   is an owner action in Bitwarden. Until it happens the credential is one line of one
   gitignored `.env`, with no owner, no expiry and no inventory row. Tracked on
   DIG-95.
3. **No scheduled ingest holds the cookie.** `git grep GLOOMBERB -- .github/workflows/`
   is empty, so the "canonical GitHub Actions `cron` env secret" named in the runbook
   does not exist. Whether the deployed `digithings-stack` Worker holds it as a secret
   is **unverified** — it needs a `CLOUDFLARE_API_TOKEN` that Security does not hold.
   That is the difference between a local experiment and production traffic, so it is
   worth one command from DevOps (DIG-1232).

No vendor was contacted. No credential was destroyed. No secret value was printed,
moved or pasted.

---

## Known gaps in this index

- **PrimeMarket is not indexed.** `docs/VENDOR_CONTENT_BOUNDARY.md` records a Prime Terminal
  artefact and sha256 from DIG-503, but no artefact was ever committed and no copy exists on any
  machine we can reach. The hash in that document is therefore not verifiable. Tracked separately —
  this index does not re-adjudicate PrimeMarket, which is DIG-461 / DIG-478 territory.
- **This index is per vendor, not per access method.** Gloom offers several surfaces (the News API,
  the MCP server, `api.gloom.sh`, the local open-source app). Only one access method is classified
  here. A later entry must classify each method separately — a key-based method and a cookie-based
  method against the same terms can land on different classifications. **Counsel's memo now
  classifies all four known methods; the per-method rows still belong here.**
- **§14 is the unresolved question for every method.** Organisation internal use is licensed only
  under a team plan, and a written agreement prevails under §21. Until one exists, no Gloomber
  access is permitted — including the 47 anonymous tools, which need no credential and are not
  fixed by destroying the cookie. Tracked in DIG-1206.
- **Terms change.** §20 lets Cold Start update the terms and change the effective date on this page.
  Re-retrieve before relying on this entry after 2026-04-05 (six months) or on any notice of change.
