# Licensing

digithings is open-core under the [MIT license](../LICENSE) (© 2026 Digi Ecosystem).
This document covers the **third-party** license obligations that attach to code we
ship, records the standing decisions for notable copyleft dependencies, and defines
the audit step for new ones. Vulnerabilities are a separate policy — see
[SECURITY.md § Dependency-audit policy](../SECURITY.md#dependency-audit-policy).

## Policy

1. **Permissive licenses are the default.** MIT, Apache-2.0, BSD, ISC and
   equivalents ship without further action.
2. **Weak copyleft requires a recorded decision.** EPL-2.0, MPL-2.0, CDDL and
   similar (file-level copyleft) may be acceptable when consumed **unmodified**
   and when the license's source-availability and notice conditions are met.
   Each acceptance is recorded below with package, version, path, and rationale.
3. **Strong copyleft is not accepted by default.** GPL, AGPL, SSPL and similar
   in shipped artifacts require an explicit human decision recorded here; the
   default answer is to replace the dependency.
4. **Modification changes the analysis.** If an EPL-/MPL-covered dependency is
   forked or patched in-tree, the modified files remain under that license and
   source availability for them becomes our obligation. Bring that to review
   before merging rather than after.

## Shipped third-party inventory (notable)

Verified against [`package-lock.json`](../package-lock.json) on 2026-09-13. This
table covers dependencies bundled into shipped client artifacts. Build- and
test-time tooling that never reaches the client output also carries weak-copyleft
licenses — MPL-2.0 `lightningcss` (via `@tailwindcss/node`, `vite`) and `axe-core`
(via `eslint-plugin-jsx-a11y`), LGPL-3.0-or-later optional platform binaries
`@img/sharp-libvips-*` (via `next` image handling and `miniflare`) — and is out of
scope here; the audit step below covers it when it changes.

| Package | Version | License | Relationship | Shipped in |
|---|---|---|---|---|
| [`beautiful-mermaid`](https://www.npmjs.com/package/beautiful-mermaid/v/1.1.3) | 1.1.3 | MIT | direct dependency of `@digithings/ui` | client bundle |
| [`elkjs`](https://www.npmjs.com/package/elkjs/v/0.11.1) | 0.11.1 | **EPL-2.0** | transitive via `beautiful-mermaid` | client bundle |
| [`dompurify`](https://www.npmjs.com/package/dompurify/v/3.4.17) | 3.4.17 | MPL-2.0 OR Apache-2.0 | direct dependency of `@digithings/ui` | client bundle |

`@digithings/ui` is [`packages/ui`](../packages/ui/package.json);
its consumer is the digithings.ai static export
(`apps/digithings-web`, built by `scripts/build-digithings.sh`).

## Decision: accept unmodified EPL-2.0 `elkjs@0.11.1` (#3964)

**Status:** accepted 2026-09-13. This closes the accept/replace question in #3964.

`@digithings/ui` depends on `beautiful-mermaid@^1.1.3`, whose `dist/index.js`
imports `elkjs/lib/elk.bundled.js`. The resolved transitive version is
**`elkjs@0.11.1`**, licensed EPL-2.0 (weak, file-level copyleft). It is bundled
into the client output of every app that uses the assistant-ui mermaid element —
`packages/ui/src/components/assistant-ui/elements/mermaid-diagram.tsx`
imports `renderMermaidSVG` from `beautiful-mermaid` — and was confirmed present in
the `digithings-web` production build while working on #3958.

Why acceptance is proportionate:

- **Unmodified.** We consume the published npm artifact as-is. No EPL-covered file
  is patched, forked, or copied into digithings-authored source, so no
  digithings-authored file becomes subject to EPL-2.0.
- **Dynamically separable.** elkjs enters the bundle through a single import
  inside `beautiful-mermaid` (`mermaid-diagram.tsx` → `beautiful-mermaid` →
  `elkjs/lib/elk.bundled.js`); it is a distinct, identifiable module rather than
  code amalgamated into our source. Replacing `beautiful-mermaid` (or routing
  around its ELK layout path) removes it from the bundle entirely, with no
  relicensing of digithings-authored code required.
- **Source availability.** Upstream source for the exact version is public at
  [github.com/kieler/elkjs](https://github.com/kieler/elkjs) (tag `0.11.1`); the
  published npm tarball carries the EPL-2.0 text (`LICENSE.md`). This record names
  the version and where to obtain the source, satisfying the EPL-2.0 §3.1
  object-code distribution condition.

**Alternative considered and rejected for now:** pin or replace
`beautiful-mermaid` with a renderer that does not pull `elkjs`, or make the ELK
layout path opt-in. Rejected because there is no permissive drop-in that preserves
the component's current render output, and because the dependency is unmodified
and separable, so acceptance is the proportionate call. **Revisit if**
`beautiful-mermaid` stops being maintained, `elkjs` is modified or forked in any
way, or its version/license changes.

## Decision: `dompurify` dual license

`dompurify@3.4.17` declares `MPL-2.0 OR Apache-2.0`. digithings relies on the
**Apache-2.0** option — a permissive license, so no weak-copyleft obligations
arise — and consumes it unmodified as a direct dependency of `@digithings/ui`,
used for SVG sanitization
([`sanitize-mermaid-svg.ts`](../packages/ui/src/components/chat/sanitize-mermaid-svg.ts)).

### Security note: five GHSAs closed by the 3.4.17 floor (DIG-5772)

The floor moved from `^3.4.15` to `^3.4.17` on 2026-10-27, and the lock now
resolves `3.4.17`. OSV lists five advisories against `3.4.15`:

| Advisory | Severity | Needs option | Fixed in |
|---|---|---|---|
| `GHSA-cg2g-xh64-v4q7` | CRITICAL | `SAFE_FOR_TEMPLATES` + shadow-root DOM output | 3.4.17 |
| `GHSA-mrv2-3pqr-j5jr` | HIGH | `IN_PLACE` + node-removing hook | 3.4.17 |
| `GHSA-6688-9rhm-gjv2` | LOW | `IN_PLACE` | 3.4.16 |
| `GHSA-c6gr-qvv4-5v3f` | LOW | `PARSER_MEDIA_TYPE: application/xhtml+xml` | 3.4.17 |
| `GHSA-p98j-92pf-mc4p` | LOW | `IN_PLACE` + node-removing hook | 3.4.16 |

None of the five was reachable at the only call site: `sanitize-mermaid-svg.ts`
passes `USE_PROFILES: {svg: true, svgFilters: true}` and `ADD_ATTR:
["dominant-baseline"]` only, so it uses none of the options above
(`RETURN_DOM`/shadow-root output included). The floor is still raised so the
audit stops reporting a critical and a high in a package we ship, and so a
future call site cannot quietly land on an affected release. Re-check if a new
call site passes `SAFE_FOR_TEMPLATES`, `IN_PLACE`, `PARSER_MEDIA_TYPE` or
`RETURN_DOM`, or if `mermaid`'s bundled sanitiser is upgraded separately.

`mermaid@11.16.0` declares `dompurify: ^3.3.3` and keeps its own bundled copy in
its dist build; that path is not changed by this floor and stays a separate
decision.

## License audit for new or upgraded dependencies

Run this before merging a PR that adds, upgrades, or replaces a dependency in a
shipped workspace (the repo root or a workspace such as `packages/ui`):

```bash
# License summary for every production dependency, resolved versions included.
npx license-checker --production --summary

# Which dependency pulled in a flagged package (version and path).
npm ls <package-name>
```

Review the output for copyleft or otherwise restrictive licenses (EPL, MPL, CDDL,
GPL, AGPL, SSPL, …). If a flagged dependency is accepted, add it to the inventory
and record a decision note in this file in the same PR; otherwise replace the
dependency. There is deliberately no CI gate for licenses yet — this is a
review-time step, and `license-checker` is run on demand via `npx` rather than
vendored as a dependency. For Python components, `pip-licenses --format=markdown
--with-urls` is the equivalent review.

## Dependency-licence register — counsel review DIG-1768 (internal ref)

**Status:** entries landed 2026-10-16 from the counsel memo (the `counsel-memo`
document on DIG-1768; DIG-1768 `done`). `DIG-###` references below are internal
issue IDs, cited for traceability as in `docs/VENDOR_CONTENT_BOUNDARY.md`.
Mastra boundary adopted by Chris ("use it behind an interface we own"); LiteLLM
PyPI-only boundary **ratified** by Chris 2026-10-07, not re-litigable at adoption
time.

Checked against the tree at `github/develop` `fb447feeb1` (2026-10-16): no
`mastra` references anywhere in tracked files; no `THIRD_PARTY_NOTICES` anywhere
in the tracked tree; compose files run the pinned `digillm` image (see the
LiteLLM entry). Wording below is Counsel's, condensed; the memo holds the clause
quotes and evidence.

### Mastra `@mastra/core` — clean at import level only (CONFIRMED)

Licence: Apache-2.0 **outside** any directory named `ee/`; everything under `ee/`
is proprietary under the Mastra Enterprise Edition License v2.0 and is not
redistributable.

**The SPDX field is unreliable for this package.** `@mastra/core/package.json`
declares `"license": "Apache-2.0"` with `"files": ["dist", ...]`, so compiled
`ee/` output ships inside the Apache-labelled tarball, and the exports map
exposes exactly `./auth/ee` and `./agent-builder/ee`. Our scanner reads this
package as clean while proprietary code sits on disk. A future scan that trusts
the SPDX field produces a false clean.

Boundary: never import an `/ee` subpath. The boundary is a directory-name
catch-all ("including but not limited to" `auth/ee`, `agent-builder/ee`),
wider than three modules — published packages carrying `ee/` include
`@mastra/core`, `@mastra/editor` and `@mastra/playground-ui` — and upstream may
recompose the set at any time (`ee/LICENSE` s.5.1), so every version bump
re-runs this check. Pin exact versions. Do not brand digithings as
Mastra-derived (Apache-2.0 s.6 grants no trademark rights). Touching `ee/` in
production without a signed agreement plus licence key is a material breach
litigated in Delaware — entirely avoidable by never importing it.

Enforcement: a CI grep for `/ee` imports, added with the first Mastra commit
(see the second open obligation below).

### MCP specification `2026-07-28` — clean (CONFIRMED)

Licence: mixed MIT / Apache-2.0 mosaic from the 2026-01-05 relicensing
transition; the `2026-07-28` spec is post-transition. Both grants are permissive
and satisfiable at once. The project is now "Model Context Protocol, a Series of
LF Projects, LLC".

Implementing a protocol is not a derivative work of it, so we owe nothing
unless we copy files. Boundary: do not vendor `schema.json`, `schema.ts` or
`schema.mdx`; generate types at build time and keep generated output out of our
MIT source tree. Position wording says **"compatible with"**, never "certified
by" or "endorsed by".

Enforcement: review-time (do not commit those three files); no CI gate.

### AutoGen — avoid: deprecated / maintenance mode; code licence is MIT (CONFIRMED)

Do not adopt: upstream README carries an explicit maintenance-mode notice
steering users to Microsoft Agent Framework — no security patches, no fixes, no
development.

**The licence is not the reason, and must not be recorded as one.** Root
`LICENSE` is CC-BY-4.0 over "documentation and other content"; `LICENSE-CODE`
is MIT over "any code in the repository", confirmed by
`python/packages/autogen-core/pyproject.toml` (`license = {file =
"LICENSE-CODE"}`). Recording CC-BY as the reason guarantees every future scan
re-reads the root `LICENSE` and re-raises a blocker that does not exist. Only a
copy of AutoGen documentation into our docs would engage CC-BY; we will not do
that.

Enforcement: none needed (no adoption); this entry exists so scans conclude.

### LiteLLM — PyPI only, never the vendor image [RATIFIED by Chris 2026-10-07]

Licence: MIT core (`litellm`, PyPI) versus proprietary `enterprise/` tree
(separate distribution `litellm-enterprise`, `LicenseRef-Proprietary`).

Boundary: install the pinned `litellm` wheel from PyPI only. Never
`docker.litellm.ai/berriai/litellm`, never `ghcr.io/berriai/litellm`, never
`litellm-enterprise`. Why the image differs from the package: the MIT core
imports the proprietary tree at runtime by source path, and the upstream
Dockerfile copies it in — running the vendor image in production is unlicensed
production use of proprietary code. PyPI is correctly labelled, so the boundary
is enforceable on the artefact. Do not enable enterprise-backed hooks in our
config (some degrade silently; one endpoint returns HTTP 400 without them).

Enforcement: `tests/scripts/test_compose_litellm_pinned.py` (landed with
DIG-1780): every compose file runs pinned `ghcr.io/digithings-ai/digillm:X.Y.Z`
built from the same exact `litellm[proxy]` version, and no tracked compose
file, Dockerfile, contract or workflow may name berriai. (Residual: two
historical prose lines still name the vendor image — `RELEASES.md:115` and the
2026-08-09 ghcr plan — neither is a compose/Dockerfile/workflow reference, so
the guard passes; cleanup belongs to their owners.)

Telemetry: the memo recorded UNSURE, pending empirical observation by Security.
Resolved by DIG-1781 (`done` 2026-10-15): observed PyPI `litellm==1.72.6` proxy
under a deny-by-default socket guard — no spend report, usage beacon,
phone-home, PostHog call, PyPI version check or `models.litellm.ai` fetch. The
single always-on outbound call is the functional public pricing-data fetch
(`raw.githubusercontent.com`; sends no usage or customer data, suppressible).
Verdict: CONFIRMED-clean for telemetry at 1.72.6. **Re-check when the pin moves
past 1.72.6.**

### Open obligations (stated, not omitted)

1. **`THIRD_PARTY_NOTICES` does not exist** — verified absent from the tracked
   tree 2026-10-16. MIT ("retain the notice in all copies") and Apache-2.0
   s.4(a)/s.4(c) (ship licence copies, retain notices) require us to ship
   dependency licence texts. On the Mastra and LiteLLM axis this is currently
   unsatisfied anywhere in the repo. CTO owns the decision: where the file
   lives, who regenerates it, and how it ships in each release artefact. The
   LiteLLM entry is being added alongside the DIG-1780 image replacement —
   coordinate with DevOps rather than duplicating.
2. **Mastra binds future code, not current code.** Nothing in the repo imports
   Mastra today; the `/ee` rule, the CI grep and the per-bump re-check attach
   to the first commit that adds it. The LiteLLM telemetry question above is the
   reverse case — an open question the register kept until evidence closed it.
