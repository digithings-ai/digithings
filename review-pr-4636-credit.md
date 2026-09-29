# In-session review — PR #4636 (credit rebuild + parity + module merge)

- Reviewer: `credit-reviewer` teammate (team `pr-4636-review`, read-only, fresh context)
- Subject: `task/4605-digichat-footer-chrome` @ `ea26fb75a` + merge `2ad549842`
  (base `module/digichat`), plus review-fix commit (this session)
- Verdict: **APPROVE-WITH-NOTES** — no blocking findings
- Severity counts: blocking 0, medium 0, low 3 (all triaged below)

## Findings (all verified)

1. Double-render — PASS (reading). Clone skins gate the two `SkinCredit`
   mounts on mutually exclusive branches (`chatgpt.tsx:50/54`,
   `claude.tsx:50/54`, `grok.tsx:46/56`, `gemini.tsx:51/76`,
   `perplexity.tsx:64/68`); stock `thread.aui.tsx` pairs
   `AuiIf(!isEmpty)` footer (`:255`) with the `isNewChatView` pin (`:213`);
   gallery `thread.aui.tsx` needs no pin — single in-flow footer
   (`:328`, `:405`).
2. Attribution opt-out — PASS (reading). `SkinCredit` nulls on
   `attribution:false` via context (`skin-credit.tsx:37`); settled embed
   flows `cfg.chrome.attribution` into `SkinChromeProvider`
   (`product-shell.tsx:318`); gate branch builds `footerSlot` only when
   `footerAttribution` (`embed-client.tsx:1190`); settled `footerSlot`
   carries no credit (`:1264-1282`).
3. Compact override — PASS (reading). `digichat.tsx:401`
   `composerLayout ?? "expanded"` → gallery default `"expanded"` (`:273`)
   with compact row layout + `ml-auto` send controls (`:672-698`, `:760`).
4. Link — PASS (reading). `href https://digithings.ai`, `target=_blank`,
   `rel="noreferrer noopener"` (`skin-credit.tsx:48-53`); anchor carries
   `pointer-events-auto` for the click-transparent empty-state pins.
5. Docs — PASS (reading). `SKIN-GALLERY.md:196-224` matches code. No
   host footer-padding overrides remain (comments only), pinned by
   baseline-isolation + product-isolation tests.
6. Tests (running): `packages/ui` 77/560 passed; `apps/digichat` 127/1319
   passed; `npm run lint` 0 errors (27 pre-existing warnings).

## Notes triaged

- (a) low, accepted: stock-thread credit hides behind the history-load
  skeleton (mixed `isEmpty`/`isNewChatView` predicates). Consistent with
  Welcome/suggestions, transient only. No change.
- (b) low, closed with evidence: settled-path opt-out default verified —
  `embed-tenants.ts:718` (`v.attribution !== false`) and
  `embed-client-config.ts:106` (default `true`); opt-out needs explicit
  `false`. No change.
- (c) low, fixed: stale `ThreadComponents.Footer` doc comment
  (`stock/thread.aui.tsx:84-87`) still said "credit removed by owner" —
  rewritten to describe the shared-credit default. Commit in this push.
