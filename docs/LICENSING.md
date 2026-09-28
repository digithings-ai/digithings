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
| [`dompurify`](https://www.npmjs.com/package/dompurify/v/3.4.15) | 3.4.15 | MPL-2.0 OR Apache-2.0 | direct dependency of `@digithings/ui` | client bundle |

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

`dompurify@3.4.15` declares `MPL-2.0 OR Apache-2.0`. digithings relies on the
**Apache-2.0** option — a permissive license, so no weak-copyleft obligations
arise — and consumes it unmodified as a direct dependency of `@digithings/ui`,
used for SVG sanitization
([`sanitize-mermaid-svg.ts`](../packages/ui/src/components/chat/sanitize-mermaid-svg.ts)).

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
