# digithings open source license and contributor policy

One page. What license we use, what contributors must agree to, how trademarks are handled.
Written by Counsel with OSS Researcher, 2026-10-04. Decision owner: Chris.

**Status: APPROVED 2026-10-04** (MIT + DCO 1.1 + register `digithings`). The analysis below is
the record of why; the decision and what it obliges us to do are in "Decision" and
"Implementation checklist". Two things changed as a result of checking the decision against
primary sources: the chain of title, and the trademark scope.

## Context

digithings is open-core. The core components (digigraph, digisearch, digiquant backtest/optimize, digichat, digikey, digiclaw, digismith, digibase single-tenant, digillm, digifetch, digidev kit core) are open source. The commercial value lives in closed add-ons: finance sub-graph implementations (research cycles, portfolio deliberation, execution), multi-tenant digibase credential broker, managed hosting, premium digidev agents/skills, and client-specific IP under `projects/`.

Source: `docs/VISION.md` § Open-source vs. managed. CONFIRMED.

The repo is currently MIT licensed (`LICENSE` © 2026 Digi Ecosystem). This document evaluates whether to keep MIT or adopt a different license for the open core, and sets the contributor policy.

## License options compared

### Option 1: MIT (current)

**What it permits:** Anyone can use, copy, modify, merge, publish, distribute, sublicense, and sell copies of the software with no restrictions beyond including the copyright notice.

**What it does not do:** No copyleft (downstream can close), no patent grant, no protection against cloud providers offering digithings as a managed service without contributing back.

**Key clause:** "Permission is hereby granted, free of charge, to any person obtaining a copy of this software … to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software."

Source: `LICENSE` in repo root. CONFIRMED.

**Trade-offs:**
- Maximum adoption friction — anyone can use it anywhere
- No patent protection for contributors or users
- No defense against a cloud provider taking the open core and selling it as a service
- Simple, universally understood, no compliance burden

### Option 2: AGPL-3.0

**What it permits:** Same freedoms as GPL-3.0, plus a network-use trigger: if you run a modified version as a service, you must make the source available to users of that service.

**What it does:** Strong copyleft that extends to network use. Protects against cloud providers offering modified digithings as a service without releasing their changes.

**Key clause (§13):** "if you modify the Program, your modified version must prominently offer all users interacting with it remotely through a computer network … an opportunity to receive the Corresponding Source of your version by providing access to the Corresponding Source from a network server at no charge."

Source: GNU AGPL-3.0 text, fetched from license-templates GitHub. CONFIRMED.

**Trade-offs:**
- Strongest protection against cloud provider exploitation
- Scares away some enterprise users who have policies against copyleft
- Compliance burden: must track and disclose all modifications
- May conflict with some internal tools or integrations
- The "network use" trigger is untested in some jurisdictions

### Option 3: Elastic License 2.0 (ELv2)

**What it permits:** Use, copy, distribute, modify, and create derivative works — but not as a hosted or managed service.

**What it does:** Source-available with a clear restriction: you cannot offer the software as a managed service to third parties. This directly protects the commercial hosting revenue.

**Key clause:** "You may not provide the software to third parties as a hosted or managed service, where the service provides users with access to any substantial set of the features or functionality of the software."

Source: Elastic License 2.0 text, fetched from elastic.co/licensing/elastic-license. CONFIRMED.

**Trade-offs:**
- Clear, simple restriction that protects the commercial hosting business
- Not OSI-approved open source — some developers and enterprises avoid it
- Restricts legitimate use cases (e.g., a company offering internal tools built on digithings to subsidiaries)
- May limit adoption in the open-source community
- Trademark clause: "Any use of the licensor's trademarks is subject to applicable law" — no trademark grant

### Summary table

| Dimension | MIT | AGPL-3.0 | ELv2 |
|-----------|-----|----------|------|
| OSI-approved | Yes | Yes | No |
| Copyleft | None | Strong (network) | None |
| Managed-service restriction | No | Yes (via copyleft) | Yes (explicit) |
| Patent grant | No | Yes (§11) | Yes (limited) |
| Adoption friction | None | High | Medium |
| Protects hosting revenue | No | Indirectly | Directly |
| Compliance burden | None | High | Low |

## Recommendation

**Keep MIT for the open core. Add a trademark policy. Use DCO for contributions.**

Rationale:

1. **The commercial moat is already protected by the open/closed split.** The finance sub-graph implementations, multi-tenant digibase, managed hosting, and premium digidev add-ons are closed. A cloud provider can take the open core but cannot offer the full commercial product without the closed components. Source: `docs/VISION.md` § Open-source vs. managed. CONFIRMED.

2. **MIT maximizes adoption of the open core.** The goal is for the core components to become the standard agentic stack. Any copyleft or restriction reduces adoption. The commercial value is in what is closed, not in restricting the open core.

3. **AGPL-3.0 would scare away enterprise users** who have policies against copyleft, for marginal additional protection. The network-use trigger is also untested for agentic AI stacks.

4. **ELv2 is not OSI-approved** and would limit community adoption. The managed-service restriction is already achieved by keeping the hosting layer closed.

5. **The real risk is not license enforcement but brand dilution** — someone offering a low-quality "digithings" service. That is a trademark problem, not a license problem.

Confidence: LIKELY. The license choice is a business decision with legal dimensions. The legal analysis is sound, but the business weighting of adoption vs. protection is Chris's call.

## Contributor policy: DCO

**Recommendation: adopt the Developer Certificate of Origin (DCO) 1.1.**

The DCO is a lightweight contributor agreement. Each commit is signed off with a `Signed-off-by:` line, certifying that the contributor has the right to submit the work under the project's license.

**Key clause (DCO 1.1):** "By making a contribution to this project, I certify that: (a) The contribution was created in whole or in part by me and I have the right to submit it under the open source license indicated in the file; or (b) The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate open source license and I have the right under that license to submit that work…"

Source: developercertificate.org. CONFIRMED.

**Why DCO over CLA:**
- **Low friction** — no paperwork, no legal review, just a sign-off on each commit
- **Sufficient for MIT** — MIT does not require a patent grant, so the DCO's certification of right-to-submit is adequate
- **Standard for open-core projects** — Linux Kernel, GitLab, and many others use DCO
- **Easy to enforce** — `git commit -s` adds the sign-off automatically

**When to switch to CLA:** If digithings adds a patent grant (e.g., by moving to Apache-2.0), or if a corporate contributor needs to grant patent rights. A CLA provides a formal patent grant and is appropriate when the project has significant patent exposure.

**Implementation:** Add to `CONTRIBUTING.md`:
```
## Contributor License Agreement

All contributions are made under the DCO 1.1. Add a sign-off line to every commit:

    git commit -s -m "feat(x): ..."

The sign-off certifies that you have the right to submit this contribution
under the MIT license. See https://developercertificate.org/.
```

## Trademark policy

**Recommendation: register "digithings" and the logo as trademarks. Do not grant trademark rights in the license.**

The MIT license does not grant trademark rights — it only covers copyright. This is correct and should be preserved. The license should explicitly state that trademarks are not covered.

**Key points:**
- The "digithings" name and logo are the trademarks. **Superseded:** the earlier draft also claimed the individual `Digi*` module names. Checked against primary sources and withdrawn — see "Trademark policy — corrected scope".
- Contributors and users may not use these marks to endorse or promote derivative works without written permission
- The license should include: "This license does not grant permission to use the trade names, trademarks, service marks, or product names of the licensor."
- Consider filing for trademark registration in the EU (EUIPO) and US (USPTO) before the public launch

Source: MIT license does not address trademarks (standard interpretation). Apache-2.0 §6 explicitly excludes trademarks. CONFIRMED.

**Implementation:** the draft `TRADEMARKS.md` is written and in "Ready-to-apply drafts" below. It supersedes the block first drafted here, which claimed trademark rights we do not have.

## Decision — APPROVED by Chris 2026-10-04

All three recommendations approved (`approve-all`, interaction `c3761e6a`). The policy is now:

1. **License for the open core: MIT.** Unchanged. No re-licensing, no relicensing of existing history.
2. **Contributor policy: DCO 1.1.** Applies from adoption forward. See "Chain of title" below — this is the part that carries the legal weight.
3. **Trademark: register `digithings` and the logo** at EUIPO and USPTO before the public launch. **Filing is Chris's action** — it costs money and commits the company, so Counsel does not file. The corrected scope is in "Trademark policy" below: do *not* assert `™` on individual `digi*` module names.

Nothing here needs a signed document, so there is no paper for Counsel to send. The items that do need someone to act are tracked in "Implementation checklist".

## Chain of title — why the DCO is not paperwork

This is the gap that decides whether outside contributions are actually usable. It was not visible in the first draft.

**The finding:** MIT is a licence the copyright holder grants **to users of the code**. It contains no grant running *from* a contributor *to* the project. `CONTRIBUTING.md` line 65 currently says "By contributing, you agree to the technical constraints above and the license terms in [LICENSE](LICENSE)" — that sentence asserts an agreement the project has no mechanism to obtain or record. The moment an outside contributor commits, the repo holds no evidenced licence from them, and the project cannot validly sub-licence that file as MIT to anyone it ships to. The file sits in the repo under a licence the contributor never gave.

**The fix, already approved:** DCO 1.1 clause (a) — "The contribution was created in whole or in part by me and I have the right to submit it under the open source license indicated in the file". That certification *is* the inbound grant. It is recorded in the commit, is verifiable with `git log`, and needs no signature service. Source: developercertificate.org, text read. CONFIRMED.

**Practical note — apply forward only.** 0 of the last 200 commits on `develop` carry a `Signed-off-by` line (checked). Do not try to backfill history. Adopt the DCO at a date, sign off from there, and say so in `CONTRIBUTING.md`; retro-signing old commits would be a fiction and would not fix anything.

**Risk if this is skipped:** a first outside PR is the moment an unproven chain of title exists. For a company whose product is the code, and whose commercial value is licensing rights to it, that is a bigger exposure than the difference between MIT and AGPL. Confidence: LIKELY (the analysis is settled; the exposure depends on whether outside contributions actually happen).

## Copyright holder name in LICENSE

`LICENSE` line 3 reads `Copyright (c) 2026 Digi Ecosystem`. **"Digi Ecosystem" appears nowhere else in the repo as a legal entity** — no company form, no VAT number, nothing (grepped across `*.md`, `*.yml`, `LICENSE`). It reads as a trade name, and a trade name is not necessarily a legal person.

**Why it matters:** the MIT grant runs from whoever owns the copyright. If the owner cannot be identified from the notice, the grant is harder to enforce against a third party and harder to prove to a customer who needs an IP indemnity. Under Italian law copyright vests in the author as a natural person (art. 22 codice civile), which for a forfettario means Chris personally — I could not read normattiva to confirm the article text this run, so treat the Italian-law detail as UNSURE; the recommendation holds regardless of jurisdiction.

**Safer wording — pick one, Chris's call:**

```
Copyright (c) 2026 <Chris Stefan>            # natural person, clearest title
Copyright (c) 2026 <Chris Stefan> trading as digithings   # person first, trade name as alias
Copyright (c) 2026 Digi Ecosystem   # keep only if a registered legal person exists
```

Editing the `LICENSE` copyright line is a change to the licence grant of a public repository, so it is Chris's decision and not a silent edit. DRAFT — not applied.

## Trademark policy — corrected scope

MIT grants copyright only. It says nothing about trademarks, and that silence is the correct default: keep it.

**The correction to the approved recommendation.** The earlier draft said "the `digithings` name, logo, and all `Digi*` module names are trademarks". Only the first two survive. Registering individual `digi*` module names is likely to fail and buys nothing if it did:

> Article 7 (Absolute grounds for refusal), Regulation (EU) 2017/1001: "The following shall not be registered: … (b) trade marks which are devoid of any distinctive character". And: "Paragraph 1(b), (c) and (d) shall not apply if the trade mark has become distinctive in relation to the goods and services for which registration is requested as a consequence of the use which has been made of it."

Source: Regulation (EU) 2017/1001 consolidated text. CONFIRMED.

EUIPO's own guidance on the same point: "distinctive character is a matter of degree, and, in assessing distinctiveness, a sliding scale applies"; a sign "is not distinctive if it is descriptive of the goods and services themselves"; and — directly on point — "A mark will not automatically have a higher degree of distinctive character just because there is no conceptual link to the relevant goods and services (16/05/2013, C-379/12 P, H.EICH / H SILVIAN HEACH)". `digichat`, `digisearch`, `digivault` are suggestive of digital goods and services. Individually they are weak, and the only route past Art. 7(1)(b) is acquired distinctiveness under Art. 7(3) — which a launch-scale project will not have on the day it files.

Source: EUIPO Trade Mark Guidelines §2.1.1 Distinctiveness. CONFIRMED (guideline text).

**What this means in practice:**
- Register **`digithings`** (word) and the **logo** (figurative). Those are the assets worth owning.
- Treat `digi*` module names as **unregistrable trade names**, protected in practice through the `digithings` mark. Do not print `™` or `®` beside them. It asserts protection that does not exist and invites a takedown we would lose.
- Confidence: LIKELY. The Art. 7 reasoning is CONFIRMED from the Regulation; whether a specific module name survives is judged per mark on its own goods and services, and I have not searched the EUIPO register for conflicting marks.

**Not checked, and it should be:** nobody has searched the EUIPO or USPTO registers for `digithings`. Someone else may already hold it, in which case the filing strategy is defensive rather than offensive and the money is better spent differently. That search is the first thing to do before spending anything — it is cheap and it can invalidate the recommendation. Recommend the Tax Specialist or CEO run the register search before any filing fee is paid.

## Implementation checklist

Approved policy is not in force until these land. None of it is urgent against an early-2027 launch, but item 1 should land before the first outside PR, not after.

| # | Item | Owner | Note |
|---|------|-------|------|
| 1 | Add DCO 1.1 to `CONTRIBUTING.md` (sign-off line, forward-only) | Counsel drafts, digidev lands | Blocking only for outside contributions, not for launch |
| 2 | Add `TRADEMARKS.md` with the corrected scope above | Counsel drafts | Text is ready in this file |
| 3 | `LICENSE` copyright line → a determinate legal owner | **Chris** | DRAFT wording above; changing a public licence grant is his call |
| 4 | EUIPO + USPTO register search for `digithings` | CEO / Tax Specialist | Do before spending any fee |
| 5 | File `digithings` word mark + logo, EUIPO and USPTO | **Chris** | Money action. Classes to confirm before filing |
| 6 | Record the DCO adoption date so forward-only is explicit | Counsel | Same PR as item 1 |

Items 3 and 5 are the only ones that need Chris. Items 1 and 2 are drafted below and need a landing PR, nothing more.

## Ready-to-apply drafts

DRAFT — written by Counsel, 2026-10-04, not yet applied to the repo. `<DATE>` is the day the DCO lands in `CONTRIBUTING.md`.

### Draft 1 — append to `CONTRIBUTING.md`

Replaces the current closing line ("By contributing, you agree to the technical constraints above and the license terms in [LICENSE](LICENSE)."), which asserts an agreement the project cannot record.

```markdown
## Contributor terms — DCO 1.1

digithings is open-core under the MIT license ([LICENSE](LICENSE)). The MIT
license covers our code; it does not grant us any rights in the code *you*
contribute. Every contribution therefore carries a Developer Certificate of
Origin 1.1 sign-off, which is the record that you have the right to submit it.

Sign off every commit:

    git commit -s -m "feat(x): ..."

or add the line automatically for this repo:

    git config --local format.signoff true

A pull request whose commits are missing the sign-off cannot be merged — add the
CI check as part of the same landing PR, or state that the sign-off is
maintainer-enforced until it is. Do not promise a gate that does not exist yet.
The full text is at <https://developercertificate.org/>.

This applies from <DATE> forward. Commits before that date are not retro-signed.
```

The last line matters: without it, the first pre-DCO commit in the history
looks like a violation rather than the start of the policy.

### Draft 2 — new file `TRADEMARKS.md`

```markdown
# Trademarks

The MIT license covers copyright only. It grants no trademark rights, and this
file does not change that.

**`digithings` and the digithings logo are trademarks.** Registration is pending
at EUIPO and USPTO. Do not use them to imply that a product, service or fork is
official, endorsed by, or affiliated with digithings, without written permission.

**`digi*` module names are not trademarks.** Names such as digichat, digisearch,
digivault, digiquant, digigraph and digikey are used descriptively to identify
these components. Do not print ™ or ® beside them — no such rights are claimed
or registered, and the marks are protected through the digithings mark instead.

If you are building on digithings, you may use the digi* names to refer to the
components you depend on. What you may not do is brand your own product or
service as though it were ours.

Questions: open an issue. Do not email about trademark use.
```

---

Sources:
- MIT license text: `LICENSE` in repo root. CONFIRMED.
- AGPL-3.0 text: gnu.org/licenses/agpl-3.0.txt (fetched via GitHub mirror). CONFIRMED.
- Apache-2.0 text: opensource.org/license/apache-2-0. CONFIRMED.
- Elastic License 2.0 text: elastic.co/licensing/elastic-license. CONFIRMED.
- BSL 1.1 text: mariadb.com/bsl11. CONFIRMED.
- DCO 1.1 text: developercertificate.org. CONFIRMED.
- Open/closed split: `docs/VISION.md` § Open-source vs. managed. CONFIRMED.
- Current contributor terms: `CONTRIBUTING.md`. CONFIRMED.
- EU trademark refusal ground: Regulation (EU) 2017/1001, Art. 7(1)(b) and Art. 7(3) (acquired distinctiveness), consolidated text. CONFIRMED.
- Weakness of descriptive marks: EUIPO Trade Mark Guidelines §2.1.1 Distinctiveness, citing C-379/12 P H.EICH / H SILVIAN HEACH §71. CONFIRMED.
- Repo checks run 2026-10-04: `LICENSE:3` copyright line; `CONTRIBUTING.md:65`; no `DCO`/`CLA`/`TRADEMARK` file in the tree; `Signed-off-by` present in 0 of the last 200 commits; "Digi Ecosystem" not present as a legal entity anywhere in `*.md`/`*.yml`/`LICENSE`. CONFIRMED.
- Italian copyright vesting, art. 22 codice civile: not verified this run (normattiva fetch failed). UNSURE.
