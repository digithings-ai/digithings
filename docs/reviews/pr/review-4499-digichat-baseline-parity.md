# Review — PR #4499 `fix(digichat): make the /baseline catalog render the first-party skin like /embed`

- **Subject:** PR [#4499](https://github.com/digithings-ai/digithings/pull/4499) — branch `task/4498-digichat-baseline-ui-polish` (tracking issue #4498)
- **Reviewed revision:** `1bed1632e` (original head); fixes landed in `6e4974ed8`
- **Reviewer:** fresh-context read-only subagent (`general`, delegation `lively-coral-raven`), 2026-09-22T21:16:22Z → 21:21:00Z. The author session did not review its own work.
- **Verdict:** APPROVE WITH NITS
- **Severity counts:** 0 blocker / 0 major / 5 minor / 3 nit

> The reviewing delegation had no shell tool, so it could not run test / lint /
> doc-check itself; it recommended CI green as the merge gate. CI was already
> green on the PR, and the post-fix runs are recorded below.

## What the change does

The `/baseline` dev catalog mounted the gallery Thread bare, so none of the
first-party theme grammar matched and ten things had drifted from `/embed`.
The change declares the `data-thread-skin="digichat"` scope marker on the
gallery Thread root (making the canonical sheet apply on every mount path),
resolves `--composer-bg` through the scoped `--card`, wires the `<html>`
theme attribute, loads Geist Mono on the baseline layout, adds the missing
Tailwind `@source`, centres `TooltipIconButton` glyphs, threads a
`suggestions` prop, mounts the canonical embed prefs host, and adds the two
docs artifacts.

## Findings

### F1 — MINOR (must fix): the "only unauthenticated route" claim was false

`docs/digichat/SKIN-GALLERY.md:93` said the baseline-chat route is "**the
one** `src/app/api/` route that does not call `requireDigiChatAuth()`".
`health`, `deploy/chrome`, `embed/tenant-config`, `mcp/oauth/callback` and
`plan-proof` also do not (each with its own gate). It also contradicted the
sibling `ONBOARDING.html`, which documents those exceptions.

**Resolution:** fixed in `6e4974ed8` — reworded to "one of the few … (with
`health`, `deploy/chrome`, `embed/tenant-config`, `mcp/oauth/callback` and
`plan-proof`)".

### F2 — MINOR: the same absolute rule repeated in the onboarding artifact

`docs/digichat/ONBOARDING.html:756` (§11 rules table) stated "Auth on every
API route except health" while §10 notes the four intentionally
unauthenticated routes.

**Resolution:** fixed in `6e4974ed8` — the table cell now enumerates the
exceptions.

### F3 — MINOR: the `suggestions` precedence comment was inverted

`packages/ui/src/components/chat/gallery-thread/thread.aui.tsx:133` said
"Runtime-provided suggestions still win". `ThreadSuggestions` does
`suggestions.length > 0 ? <static> : <ThreadPrimitive.Suggestions>`, i.e. the
**static** list wins and the runtime is the fallback — and
`skins/digichat.tsx:293` always passes a non-empty list.

**Resolution:** fixed in `6e4974ed8` — the comment now states static takes
precedence.

### F4 — MINOR: stale scope-marker comment

`packages/ui/src/styles/chat-aui.css:496` claimed "/baseline mounts the
gallery Thread without `.aui-theme-stage` or `[data-thread-skin]`" — false
after this very change adds the marker.

**Resolution:** fixed in `6e4974ed8` — the comment is rewritten as
belt-and-braces and the rule is kept.

### F5 — MINOR: the PR body overstated the `chat-aui.css` change

The caret block was appended and then deleted within the same session, so it
netted out; the diff is only the full-bleed width change. Not a code defect.

**Resolution:** fixed — the PR body was corrected via `gh pr edit 4499`.

### F6 — MINOR (under-disclosed): the width change is shared, not baseline-only

Removing `max-width`/`margin-inline` from `.digichat-thread` also affects the
product `app`/`modal`/`sidebar` modes (previously centred at 44rem, now
full-bleed canvas with the content column still 44rem). Intentional per the
body, but the title framed it as a `/baseline` fix.

**Resolution:** disclosed — the PR body now calls this out explicitly. Left
as-is behaviourally; it is a deliberate product-wide visual change.

### F7 — NIT: `StaticSuggestionItem` key collision

`key={prompt}` collides when two prompts are identical.

**Resolution:** fixed in `6e4974ed8` — `key={`${index}:${prompt}`}`.

### F8 — NIT: duplicate `--composer-bg` declaration

The Thread root's inline `--composer-bg` overrides
`.digichat-thread { --composer-bg: var(--surface) }`; both resolve to the same
token now. Optional cleanup.

**Resolution:** accepted — not actioned (no behavioural difference).

### F9 — NIT: light-mode first-paint flash

`baseline-client.tsx` sets the theme in a `useEffect`, so there is a brief
flash before `<html>` gets `data-theme`. Dev-only surface, and a conscious
trade-off: the baseline isolation test forbids `data-theme` in `layout.tsx`.

**Resolution:** accepted — not actioned.

## Verified clean (coverage record)

- The composer token fix resolves the same value for the plain `base` skin
  (`baseline.css` `:root --card`).
- **Declaring `data-thread-skin="digichat"` on the shared gallery Thread root
  is safe**: only the `digichat` skin renders that Thread
  (`skins/digichat.tsx:22,291`; `skins/index.tsx:73-75` is an explicit branch;
  the other 11 skins render their own components; `product-shell.test.tsx`
  `75/94/160` asserts the attribute on the shell wrapper, not the Thread).
- `tooltip-icon-button.tsx`'s new `inline-flex` breaks no caller.
- The `suggestions` prop threading is complete
  (`ThreadProps → ThreadChrome → Thread → ThreadRoot → ThreadSuggestions`, and
  `DigichatThreadProps → DigichatThread → Thread`) and `ThreadSuggestions`
  sits under `ThreadChromeContext.Provider`.
- `StaticSuggestionItem` uses the same
  `aui.thread.append({ content, runConfig: aui.composer.getState().runConfig })`
  plus `isRunning` guard idiom as `skins/base/thread.tsx`'s `sendPrompt`.
- The `@source "../../../../../packages/ui/src/components/chat"` path math is
  correct and its comment contains no `@digithings/` (the isolation test does
  a whole-file regex scan).
- `useStockChatPrefs` uses no assistant-ui hooks, so mounting it above
  `AssistantRuntimeProvider` is safe; only `skins/digichat.tsx` reads
  `useEmbedChatPrefsOptional`.
- The selector-pinning tests (`chatbot-css.share.test.ts`,
  `gallery-thread.source.test.ts`) remain satisfied.
- Docs spot-checks hold: the 12 skin ids, the first-party host/slug mapping,
  the upstream pin `https://digithings.ai/api/chat` with a fail-closed
  override, the loopback + dev gate, version 2.3.2, the least-privilege
  `DEFAULT_CLIENT_CONFIG`, and the "19 commands" count (21 `SLASH_COMMANDS`
  defs minus 7 filtered plus 5 featured languages).
- No capitalized Digi names, no debug/dead code, no unused imports in the diff.

## Evidence inspected

`github_get_commit(1bed1632e, include_diff)`,
`github_pull_request_read(#4499, get_diff)`, plus local reads of
`thread.aui.tsx`, `DigichatThread.tsx`, `skins/digichat.tsx`,
`skins/index.tsx`, `skins/base/thread.tsx`, `skins/base-assistant-ui/*`,
`thread-skins.ts`, `baseline-client.tsx`, `(baseline)/layout.tsx`,
`baseline.css`, `chat-aui.css`, `web-theme.css`, `chatbot.css`,
`tooltip-icon-button.tsx`, `attachment.aui.tsx`, `block-caret.tsx`,
`product-shell.tsx`, `product-shell.test.tsx`, `stock-chat-prefs-host.tsx`,
`embed-chat-prefs.tsx`, `client-projection.ts`, `baseline-embed.ts`,
`baseline-preview.ts`, `api/baseline-chat/route.ts`, `product-chrome.css`,
`apps/reference/app/(chatbot)/chatbot/chatbot.css`,
`apps/digichat/config/examples/*`, `apps/digichat/AGENTS.md`,
`docs/digichat/SKIN-GALLERY.md`, `docs/digichat/ONBOARDING.html`.

## Verification after the fixes (`6e4974ed8`)

- `packages/ui` `npm run test` → 62 files / 447 tests passed
- `apps/digichat` `npm run test` → 126 files / 1250 tests passed
- `apps/digichat` `npm run lint` → 0 errors (30 pre-existing warnings)
- `make doc-check` → OK (417 markdown files scanned)
