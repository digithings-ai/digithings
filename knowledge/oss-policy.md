# digithings open source license and contributor policy

One page. What license we use, what contributors must agree to, how trademarks are handled.
Written by Counsel with OSS Researcher, 2026-10-04. Decision owner: Chris.

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
- The "digithings" name, logo, and all Digi* module names are trademarks of Digi Ecosystem
- Contributors and users may not use these marks to endorse or promote derivative works without written permission
- The license should include: "This license does not grant permission to use the trade names, trademarks, service marks, or product names of the licensor."
- Consider filing for trademark registration in the EU (EUIPO) and US (USPTO) before the public launch

Source: MIT license does not address trademarks (standard interpretation). Apache-2.0 §6 explicitly excludes trademarks. CONFIRMED.

**Implementation:** Add to `LICENSE` or a separate `TRADEMARKS.md`:
```
## Trademarks

"digithings", the digithings logo, and all Digi* module names are trademarks
of Digi Ecosystem. This license does not grant permission to use these marks.
```

## The 3 decisions Chris must make

1. **License for the open core:** Keep MIT (recommended), or switch to AGPL-3.0 or ELv2? The recommendation is MIT because the commercial moat is the closed add-ons, not license restrictions. If Chris wants stronger protection against cloud providers, AGPL-3.0 is the strongest option but will reduce adoption.

2. **Contributor policy:** Adopt DCO 1.1 (recommended), or use a formal CLA? DCO is simpler and sufficient for MIT. CLA is better if we later add patent grants or have corporate contributors with patent concerns.

3. **Trademark registration:** File for EUIPO and USPTO trademark registration before the public launch (recommended), or defer? Filing before launch prevents brand dilution and is relatively low cost. Deferring risks someone else filing first.

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
