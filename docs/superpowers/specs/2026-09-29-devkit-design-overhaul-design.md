# digichat devkit design overhaul — spec

- Date: 2026-09-29
- Route: dev-only `/devkit` (apps/digichat). Stays dev-only; no production surface change.
- Layout decision: keep two-pane (sidebar editors + live chat right pane).
- Approach: A — kit-native rebuild (reference-gallery patterns + kit controls), full scope, no phased slice.
- Status: all 7 design sections approved by user in chat (§1 yes continue; §2 continue; §3 looks good, continue; §4 good, custom colors allowed; §5 good, continue; §6 looks good; §7 good). Revised per subagent review findings (all 5 blockers + majors addressed; claims verified against source).

## §1 Shell + scroll-spy nav

- Sidebar gains a sticky group nav at top with exactly three items: Basics / Appearance / Advanced (groups defined in §2).
- Disclosure level: the 3 groups are the only collapsible level. The 8 existing sections render inside their group as always-expanded subgroups (non-collapsible headings with anchor ids). No nested collapsibles.
- Groups use the reference-gallery single-open disclosure (`apps/reference/components/controls/accordion-reference.tsx`): kit `Collapsible` + `CollapsibleTrigger`/`CollapsibleContent`, one `openGroup: string | null` in state, `open={openGroup === id}`, `onOpenChange={(isOpen) => setOpenGroup(isOpen ? id : null)}`, chevron keyed off the Collapsible root's open state (exact selector per the specimen at build time), panel animation via measured height (`data-open:h-[var(--collapsible-panel-height)]`, `motion-reduce:transition-none`).
- Interaction rule (normative): at most one group is open. Manual trigger toggle is the only path that may close: toggling the open group sets `openGroup` to `null`. The IntersectionObserver may change *which* single group is open but MUST never set `openGroup` to `null` — it opens the visible group (closing the previous one only as the single-open invariant requires) and never collapses the visible group. A manual close persists until the scroll position crosses into a different group.
- Clicking a nav item sets `openGroup` to that group and smooth-scrolls to the group anchor (`scrollIntoView({ behavior, block: "start" })`, `behavior` is `auto` under reduced motion).
- Scroll-spy config (normative): one `IntersectionObserver` over the three group anchors, `root` = sidebar scroll container (fallback `null`), `rootMargin: "-20% 0px -65% 0px"`, `threshold: 0`. The group whose anchor is foremost in the active band is the visible group. Active nav state follows `openGroup`; nav clicks and the observer write to the same `openGroup` value.
- Reduced motion (normative): under `@media (prefers-reduced-motion: reduce)`, nav smooth-scroll degrades to `auto` and all nav-highlight and collapsible height transitions are `transition-none` (`motion-reduce:transition-none` on trigger chevron, content, and nav link).
- Nav chrome and active style in canon tokens only: container `bg-surface border-b border-hair`; labels `font-mono`; inactive link `text-ink-mute hover:text-ink`; active link `text-accent bg-accent/10 border-l-2 border-accent` (no custom hex).

## §2 Regrouping map (nothing dropped)

- The 8 existing sections keep their exact titles and commit paths; only grouping changes. All 8 subgroup anchors stay addressable (`id` per section, `scroll-mt-*` offset); nav targets the 3 group anchors.
- Basics: Identity, Features, Models.
- Appearance: Appearance — single section retaining all current controls: skin, theme, mode, title, welcome title/body, composer placeholder, starter suggestions, accent color + accent foreground, attribution credit, launcher mode/hotkey/label, reply-language default, user-bubble alignment.
- Advanced: Backend, Tools, MCP servers, Gate (titles verbatim; no renames).
- Completeness invariant: Identity, Backend, Appearance, Features, Models, Tools, MCP servers, Gate each appear exactly once, each under its §2 group, each subgroup always expanded.

## §3 Kit control mapping

Replace bespoke rows with kit parts imported from `@digithings/ui/ui` (Field, Input, Textarea, Switch, SegmentedControl, Select + SelectContent/Group/Label/Separator/Item/Trigger/Value with portal SelectContent, Button, IconButton, Card + CardHeader/Title/Content/Footer), following `apps/reference` specimens (`controls/select-reference.tsx`, `controls/accordion-reference.tsx`, `controls/dialog`, `dropdown`, `form-fields`, `nav-buttons`, `search-bar`, `slider`, `tags-input`, `tooltip`; `components/ui` kit-surface-reference):

- TextRow → Field + Input
- TextListRow → Field + Textarea
- BoolRow → Field + Switch
- TriRow → SegmentedControl (`inherit` / `on` / `off`)
- SelectRow → kit Select (portal `SelectContent` + Group/Label/Separator/Item, per `select-reference.tsx`)
- SecretRow → Field + password Input + Button (replace/clear)
- clear ✕ → IconButton
- tool / server cards → Card + Button / IconButton
- backend type → Select (never SegmentedControl: 9 variants plus a confirm-discard flow need a trigger, not cells)

The existing `commit`/`onCommit` boolean-return contract is unchanged (applied → `true`; refused → `false` + row reverts display + `editNotice` in `devkit-client.tsx`) — kit parts only change rendering, not the draft-text pipeline.

**Controlled rule.** Every SelectRow, TriRow, and SegmentedControl row MUST be controlled: `value` comes from `draft.parsed` (backend-type row: from the existing `backendType` mirror state + resync effect), and `onValueChange`/`onChange` calls `onCommit` with no local state update of its own. On `false` the row performs no state update, so re-render snaps the display back — no `e.target.value = …` DOM assignment in these rows. The backend-type row keeps its confirm: cancel or refused commit returns `false` and never calls `setBackendType`. TextRow / TextListRow / BoolRow keep today's uncontrolled + direct-DOM-revert pattern (`e.target.value` / `e.target.checked` restore); only Select/Tri/Segmented convert.

**Dress pinning.** `dress="chat"` on Input (all TextRow inputs incl. SecretRow password field and add-tool/add-server inputs), on Button (Set/Cancel/Add/Replace/save-adjacent row buttons), and on the Card root only (Header/Title/Content/Footer inherit via context — never pin parts individually). Everything else uses default kit utilities: Select, Switch, and Field expose no `dress` prop; Textarea exposes no `dress` prop (chat tone there comes from `devkit-controls.css` overrides only, never a kit change); SegmentedControl's `dress` is `"reference" | "accent"` only (no `"chat"`) — devkit rows use the default `"reference"`; clear-✕ IconButtons use defaults.

**Select-vs-SegmentedControl rule.** SegmentedControl iff ALL hold: 2–3 options, static set, short single-token labels that fit mono cells, commit without confirmation. That is exactly: all TriRows (`inherit`/`on`/`off`), theme (`dark`/`light`), transcript `userAlign` (`right`/`left`), `auth` (`anonymous`/`session`), `persistence` (`none`/`memory`/`server`), launcher `mode` (`inherit`/`dot`/`bar`), reasoning override (`auto`/`collapsed`/`open`), page context (`off`/`silent`/`visible`). Everything else is Select: every ≥4-option set, every dynamic/grouped list (skin, reply-language incl. current-value-appended option, model lists), every long/underscore-token enum that fails the label-fit test (gate `mode`, `llmAccess`, `requiredPlanTier`, chain-of-thought `view`), and backend type (excluded by fiat: 9 options + destructive confirm).

**Field + SegmentedControl a11y carve-out.** Field injects `id` / `aria-describedby` / `aria-invalid` into its child via clone and pairs the label via `htmlFor` — meaningless on a `role="group"` div of buttons (SegmentedControl renders `role="group"` + `aria-pressed` buttons, deliberately not a tablist). SegmentedControl rows MUST NOT nest inside Field as the cloned child. They render the group pattern instead: a `span` label carrying a generated id, `SegmentedControl` with `aria-labelledby={labelId}` (plus `aria-describedby` pointing at the hint/error element ids when present), hint/error text in Field's mono micro styling via devkit-scoped classes. All other rows keep Field's default label→control injection.

**SecretRow + non-text flows.** SecretRow keeps its local `replacing`/`val` state outside the draft: `onReplace` returning `false` (validation refusal or save-in-flight) stays open and keeps the typed value; `true` clears `val` and closes. `onClear` (secret `deleteKey`/`deleteListItemField`) commits immediately — no revert state exists since the masked line (`not set` / `•••••• (preserved from file)` / `•••••• (custom value — never shown)`) derives from `secretState`/`secretStateInList`, never from a displayed value. Secret values never surface in `draft.issues` text. Add-tool / add-server forms keep local `useState` inputs; Add commits via `appendListItem` — success resets the local fields, refusal keeps them plus the client `editNotice`. Row/card remove-✕ buttons commit `removeListItem` / `deleteListItemField` / `deleteKey` directly with no revert path.

## §4 Swatch pickers (accent color + foreground)

- Presets are defined once in `ACCENT_SWATCH_PRESETS` in `apps/digichat/src/app/(devkit)/devkit/devkit-editors.tsx` (next to the existing hex validation), as 10 `{ name, token, hex }` entries pinned to canon `--accent-<module>` hexes from `packages/design/tokens.css` (`:root`, theme-independent):
  digigraph `#e5b765`, digiquant `#3dd6c4`, digisearch `#5aa3c4`, digichat `#e2708a`, digikey `#d97a5a`, digismith `#6fa3a3`, digiclaw `#b87840`, digibase `#9ea0a5`, digistore `#7b7fc7`, digivault `#9d8fc9`.
- Selection rule: research / portfolio / execution are excluded (their accents collapse to `--ink` under `:root[data-theme]` by design — ruled 2026-07-08, they name langgraphs not colored products — so they are not colors); digilink is excluded to hold the list at 10. Each preset commits its literal hex (never a `var()` reference), so the stored value is theme-stable.
- A "Custom…" entry opens a native `<input type="color">`. The color input emits lowercase `#rrggbb`; the value is lowercased before commit and validated by the existing `/^#[0-9a-fA-F]{6}$/` check. Stored format is always lowercase `#rrggbb`. Anything failing the regex is rejected (commit returns `false`, display reverts, no draft write) — this covers invalid custom values identically to invalid typed hex.
- Accent color + accent foreground render side-by-side with a live contrast-ratio readout. The ratio uses the WCAG 2 relative-luminance formula (the same `luminance`/`contrast` helpers as `packages/ui/src/styles/contrast.contract.test.ts`: sRGB linearization, `L = 0.2126R + 0.7152G + 0.0722B`, ratio `(L1 + 0.05) / (L2 + 0.05)`), computed client-side in the editor.
- Readability threshold is WCAG AA **4.5:1** (matches the repo's `AA_TEXT = 4.5` canon contract in the same file). Below 4.5:1 a non-blocking warning shows: `Contrast {ratio}:1 is below the 4.5:1 (WCAG AA) minimum — text on this accent may be hard to read.` The warning is dismissible; dismissal is local editor state and resets whenever either value changes. A low-contrast pair still commits (warning, not block).
- Every swatch interaction (preset click, custom pick) commits through the existing `onCommit` path with identical validation + revert semantics: `true` applies, `false` reverts the swatch highlight to the last-committed value. Preset clicks pass the preset hex through the same regex gate before `scalar(["chrome", "accent", "color"|"foreground"], v)`.

## §5 Devkit-scoped CSS

- New file `apps/digichat/src/app/(devkit)/devkit-controls.css` (the `(devkit)` route group is the dev-only home). Imported ONLY by `apps/digichat/src/app/(devkit)/layout.tsx`, after `../(baseline)/baseline.css`.
- Import allowlist (this order is normative, per the `controls-core.css` header lines 39-44): `tailwindcss` is already provided by `baseline.css` and MUST NOT be re-imported; the new file contains exactly:
  1. `@import "@digithings/design/tokens.css";`
  2. `@import "@digithings/ui/styles/web-theme.css";`
  3. `@import "@digithings/ui/styles/controls-core.css";`
  4. `@import "@digithings/ui/styles/controls-overlay.css";`
  5. the kit `@source` line for the controls components (required by the `controls-overlay.css` header, MIGRATION.md rule 3), mirroring the `baseline.css` `@source` convention.
- Rationale (verified, not assumed): `baseline.css` imports only tailwindcss, tw-animate-css, `digichat-app-theme.css`, and the assistant-ui template sheet — it provides NO canon tokens and NO `dress="chat"` tone. `digichat-app-theme.css` bridges shadcn slots only; the `text-ink` / `bg-surface` / `border-hair` utilities (§1 nav chrome) exist solely via the `web-theme.css` `@theme inline` bridge, and `controls-core.css` reads `var(--hair)` / `--ink` / `--surface` (plus `--accent`, `--danger`, `--bg`) throughout. The token-class and chat-dress claims are therefore kept, grounded by imports 1-2. Nothing is dropped.
- Canon vars (`--ink`, `--surface`, `--hair`, …) resolve only under `:root[data-theme]`; `layout.tsx` stays `data-theme`-free per the isolation test. The devkit content root (page/client wrapper, NOT the root layout) carries `data-theme="light"` so the imported tokens resolve inside the devkit subtree only.
- Devkit-prefixed overrides only (all other rules forbidden in this file): `.devkit-side` width floor (inline `sidebarWidth` style remains the source of truth; CSS sets `min-width: 16rem` / `max-width: 32rem` clamp), `.devkit-navlink[aria-current="true"]` scroll-spy active state (`color: var(--ink); background: color-mix(in oklab, var(--accent) 12%, transparent)`), `.devkit-swatches` grid (`display: grid; grid-template-columns: repeat(5, 2rem); gap: 0.5rem`), `.devkit-swatch` cells (`width/height: 2rem; border: 1px solid var(--hair)`; `[aria-pressed="true"]` gets `outline: 2px solid var(--accent); outline-offset: 2px`), density (`.devkit-compact` halves editor row gaps).
- Zero changes to `baseline.css`, any kit stylesheet, or any production surface. No `@digithings/ui` component changes are allowed — kit parts (Field, Input, Switch, SegmentedControl, Select, Button, IconButton, Card) are consumed as-is; all devkit styling rides the new file.
- `devkit-isolation.test.ts` is extended: assert `layout.tsx` imports `devkit-controls.css`, and keep forbidding `globals.css`, `Providers`, theme script, and `accent-*` classes in the devkit route.

## §6 Chat preview touch-ups

- Shared header strip: the existing mono span becomes `{slug} · {skin} · {theme}` (`slug` first, from the last-valid `deployment.slug` the preview already receives; `·`-separated, same `font-mono` span, existing default-model suffix and theme toggle untouched). The unsaved-changes dot keeps its position and behavior.
- Validation-state parity: a slim warning bar renders inside the preview pane directly beneath the header strip (above the chat surface, full-bleed, devkit-scoped CSS only — compact single-line `font-mono text-[11px]`, `border-b border-destructive/50 text-destructive`, `role="alert"`). It is sourced from the same `draft.issues` array the sidebar list renders — `DevkitPreview` takes a new `issues: string[]` prop threaded from `devkit-client.tsx`; no second validation path. Show rule: visible iff `issues.length > 0`; hidden (unmounted, no reserved space) iff empty.
- Last-valid hold is unchanged: the preview keeps rendering `draft.parsed` (the `withValidation` fold), so an invalid draft holds the last-valid deployment behind the bar. Test hooks: `data-testid="devkit-preview-invalid-bar"` on the bar and `data-preview-slug={deployment.slug}` on the preview root, so a test can assert an invalid edit shows the bar while the held slug is still rendered.
- No structural changes to the validate flow or preview props beyond the added `issues` prop.

## §7 Testing

**Unit — `apps/digichat` (`npm run test` in `apps/digichat`):**

- Regrouping completeness: every current control is present under its new Basics / Appearance / Advanced group; all 8 section anchors remain addressable; commit paths are invariant (same `onCommit` ids, grouping only).
- Scroll-spy semantics: observer opens the visible group and never closes (manual open/close state is never fought); clicking a nav item opens its group and smooth-scrolls to its anchor.
- Row-mapping parity: each §3 mapping (TextRow, TextListRow, BoolRow, TriRow, SelectRow, SecretRow, clear ✕, tool/server cards, short option sets, backend type) keeps the `commit`/`onCommit` contract — valid applies and returns `true`; refused returns `false` and the row reverts its display.
- Swatches: preset hexes match the §4 const; contrast warning fires below 4.5:1; invalid custom value is refused (`false`) and reverts to the prior value.
- §6 preview: header shows deployment slug next to `skin · theme` plus the unsaved-changes dot; preview-pane warning bar mirrors `draft.issues`; preview holds last-valid on an invalid draft.
- Isolation (`devkit-isolation.test.ts`): asserts `DevkitEditors` + kit `Collapsible` (no `<details>`), kit `Select` (no native `<select>`/`<optgroup>`), `<textarea>` retained for raw YAML; CSS allow — layout imports the new devkit CSS file, which imports kit `controls-core.css` + `controls-overlay.css`; CSS deny — no `globals.css` / `Providers` / theme script / accents, and no unprefixed devkit selectors leaking outside devkit scope.
- Gating (no new production surface): existing save/validate/configs route tests assert 404 in production (`NODE_ENV=production`) and 404 off-loopback in development (non-loopback host) via `isLocalBaselinePreview`; devkit page asserts the `notFound` + `force-dynamic` dev-only boundary. This work adds no route and changes no gate; these tests must stay green.

**Suites + CI gates:** `npm run test` + `npm run lint` in `apps/digichat` clean; full `apps/digichat` + `packages/ui` suites green; frontend canon guard clean; prod build (`npm run build` in `apps/digichat`) green.

**Browser pass — dev box only (loopback):**

1. Open `/devkit`, scroll the sidebar → nav highlight follows the visible group; manually closed group is never force-reopened except by scroll/click into it.
2. Click each nav item → its group opens and smooth-scrolls into view.
3. Edit one control per group → invalid value shows the preview-pane warning bar and blocks save; valid value validates, saves, and the chat preview reflects the saved deployment; header slug/dot update accordingly.
4. Custom color round-trip: pick preset, then Custom custom hex, save, reload → value persists; invalid custom entry reverts.
5. Export popup: open, switch tabs, attempt export of a sentinel-bearing draft → still client-side only (no `/api/devkit/export`) and sentinel-blocked.

Pass criteria: all five steps behave as stated, with zero console errors and no change to any production surface.

## Out of scope (explicit)

- Public/authenticated devkit access (deferred to its own planned issue).
- Chat-preview reflection projection gaps (separate follow-up; §6 touch-ups only).
- Any change to `baseline.css`, kit stylesheets, product shell, or embed surfaces.
