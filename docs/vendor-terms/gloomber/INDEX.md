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
