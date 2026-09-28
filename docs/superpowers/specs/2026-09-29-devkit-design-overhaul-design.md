# digichat devkit design overhaul — spec

- Date: 2026-09-29
- Route: dev-only `/devkit` (apps/digichat). Stays dev-only; no production surface change.
- Layout decision: keep two-pane (sidebar editors + live chat right pane).
- Approach: A — kit-native rebuild (reference-gallery patterns + kit controls), full scope, no phased slice.
- Status: all 7 design sections approved by user in chat (§1 yes continue; §2 "contiue"; §3 "looks good, continue"; §4 "good, custom colors should be allowed"; §5 "good, continue"; §6 "looks good"; §7 "good").

## §1 Shell + scroll-spy nav

- Sidebar gains a sticky group nav at top: Basics / Appearance / Advanced (see §2).
- Scroll position drives nav highlight via IntersectionObserver over group anchors.
- Observer auto-opens the visible group; it only opens, never closes (user's manual
  open/close state is never fought).
- Clicking a nav item smooth-scrolls to that group's anchor and opens it.
- Groups use the reference-gallery single-open disclosure pattern (kit Collapsible +
  CollapsibleTrigger/Content, open index in state, chevron via group-data-open,
  measured-height animation — see apps/reference controls/accordion-reference.tsx).
- Canon token classes for nav chrome: text-ink/ink-soft/ink-mute, bg-surface,
  border-hair, font-mono kicker labels.

## §2 Regrouping map (nothing dropped)

Current 8 accordion sections regroup into 3 nav groups:

- Basics: Identity, Models, Features
- Appearance: Brand, Welcome, Color
- Advanced: Backend, Tool catalog, MCP servers, Access

Every existing control keeps its commit path; only grouping changes. The 8 section
anchors remain addressable (nav targets groups; groups contain the existing sections
as subgroups).

## §3 Kit control mapping

Replace bespoke rows with kit parts imported from `@digithings/ui/ui`
(Field, Input, Textarea, Switch, SegmentedControl, Select + SelectContent/Group/
Label/Separator/Item/Trigger/Value with portal SelectContent, Button, IconButton,
Card), following apps/reference specimens (controls/select-reference.tsx,
controls/accordion-reference.tsx, controls/dialog, dropdown, form-fields,
nav-buttons, search-bar, slider, tags-input, tooltip; components/ui kit-surface-reference):

- TextRow → Field + Input
- TextListRow → Field + Textarea
- BoolRow → Field + Switch
- TriRow → SegmentedControl (inherit / on / off)
- SelectRow → kit Select
- SecretRow → Field + password Input + Button (replace/clear)
- clear ✕ → IconButton
- tool / server cards → Card + Button / IconButton
- short option sets → SegmentedControl
- backend type → Select

Keep the existing `commit`/`onCommit` boolean-return contract (applied → true;
refused → false + row reverts display) — kit parts only change rendering, not the
draft-text pipeline.

## §4 Swatch pickers (accent color + foreground)

- 8–10 preset swatches drawn from canon tokens, defined once in a single const
  (preset hexes + names).
- "Custom…" entry opens a native color input; custom values allowed (user-approved).
- Accent color + accent foreground rendered side-by-side with a contrast-ratio
  warning when the pair falls below readability threshold.
- Swatch selection commits through the existing `onCommit` path (same validation +
  revert semantics as today).

## §5 Devkit-scoped CSS

- New file (e.g. `devkit-controls.css`) imported ONLY by the devkit layout.
- It imports kit `controls-core.css` + `controls-overlay.css` — the source of the
  `dress="chat"` tone, which `baseline.css` does not provide today (devkit route
  uses (baseline)/baseline.css: tailwindcss + tw-animate-css + digichat-app-theme +
  assistant-ui template CSS + @source chat catalog; kit shell styles arrive via
  styles/chat-shell-cli.css in the product shell, which devkit isolation forbids).
- Plus devkit-prefixed overrides only: sidebar width/scroll, scroll-spy active link,
  swatch grid, density.
- Zero changes to baseline.css, kit stylesheets, or any production surface.
- Isolation test (`devkit-isolation.test.ts`) extended to assert the devkit CSS
  import and keep forbidding globals.css / Providers / theme script / accents.

## §6 Chat preview touch-ups

- Shared header strip: show the deployment slug next to `skin · theme`, plus the
  existing unsaved-changes dot.
- Validation-state parity: slim warning bar inside the preview pane when the draft
  is invalid, reusing the same `draft.issues`; preview keeps holding last-valid
  (no behavior change).
- No structural changes to the validate flow or preview props.

## §7 Testing

- Unit coverage grows inside existing suites: regrouping completeness test (every
  current control present under its new group), swatch preset hex/contrast tests,
  isolation test asserts the new CSS file.
- Browser pass on the dev box: every group edits → validates → saves with live
  chat reflection; scroll-spy tracking; custom color round-trip; export popup
  unchanged (still client-side, sentinel-blocked).
- Gates: `npm run test` + `npm run lint` in apps/digichat, frontend canon guard
  clean, full suites in apps/digichat + packages/ui, prod build green.
- No new production surface: dev-only gating and loopback save gating untouched.

## Out of scope (explicit)

- Public/authenticated devkit access (deferred to its own planned issue).
- Section-7 live-preview reflection projection gaps (separate follow-up).
- Any change to baseline.css, kit stylesheets, product shell, or embed surfaces.
