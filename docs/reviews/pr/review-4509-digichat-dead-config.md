# Review — PR #4509 (digichat Phase 2a: drop dead config surface)

- **Subject:** PR #4509 — `task/4508-digichat-dead-config` → `module/digichat`
- **Reviewed revision:** `f34e7038d`
- **Review fixes:** applied in the follow-up commit on the same branch
- **Tracking issue:** #4508
- **Reviewer:** independent fresh-context read-only subagent (`general`, delegation
  `gentle-indigo-lynx`, 2026-09-22T22:10:03Z → 22:12:04Z). The author session did not
  review its own work.

## Verdict

**APPROVE WITH NITS** — 0 blocker / 0 major / 1 minor / 3 nit.

The reviewer had no shell in its sandbox, so it reconstructed the diff through the
GitHub API (`github_pull_request_read(4509, get_diff)`) and verified with read-only
tools. It did not execute the test suites; CI is the gate for that.

## Findings

| # | Severity | Location | Finding | Resolution |
|---|---|---|---|---|
| F1 | minor | `docs/architecture/digichat-config-program-plan.md` (retained list, `cli.enabled`) | The retain justification called `cli.enabled` "advisory metadata by design … the web app never imports Ink". It has a live consumer: `apps/digichat/cli/src/chat-request.ts:76` (`assertCliEnabled`) throws when it is not `true`, and `ARCHITECTURE.md:1429` says "Documents / **gates** the Ink CLI". The retain decision is right; the "advisory" framing invites a future deletion. | **Fixed** — the bullet now cites the live CLI consumer and the `.strict()` schema. |
| F2 | nit | plan doc (retained list, `layout`) | "not a dead derived value" is true for the tenant field (it drives `chromeMode` at `loader.ts:75`) but the *client-projected* `layout` is computed and never read. | **Fixed** — the bullet now splits the tenant field (live) from the client projection (unread). |
| F3 | nit | plan doc (operating rules) | Pre-flight still pinned at "126 files / 1250 tests"; this PR moves it to 125 / 1248. | **Fixed** — counts updated. |
| F4 | nit | `docs/superpowers/plans/2026-09-17-shadcn-wave-4.md:69` | A dated historical plan still lists `stock/stock-chrome-bar.tsx`. | **Accepted** — a dated snapshot; not edited. |

## Verified clean by the reviewer

- **`StockChromeBar` is genuinely dead.** No importer or barrel export remains. The only
  references are the two absence-assertions the change cites:
  `apps/digichat/src/app/(baseline)/baseline-isolation.test.ts:44` and
  `apps/digichat/src/app/(digichat)/embed/embed-slash.test.tsx:27`.
- **The client-projected `activityDetail` is genuinely dead.** Removed from the type
  (`client-projection.ts:95-102`), `DEFAULT_CLIENT_CONFIG` (`:150-155`) and the mapping
  (`:231-238`). `.activityDetail` survives only server-side (`route.ts:281,518`,
  `loader.ts:131,161`, `embed-tenants.ts:343-346,520`, both adapters). Client gate
  readers (`stock-chat-prefs-host.tsx:58-59`, `tool-catalog-bar.tsx:42`,
  `chat-panel.tsx:76`) touch only `webSearch`/`showByok`.
- **No generic/spread access to the removed field** — no `Object.entries(...gate)`, no
  `...cfg.gate`; `embed-bridge.ts:80-88` rebuilds `gate` explicitly, and
  `toChromeClientConfig` spreads `chrome`, not `gate`. The embed path already omitted it
  (`embed-client-config.test.ts:162` asserts its absence). Removing it cannot change
  client behaviour.
- **Server keeps `activityDetail`** — `route.ts:281` (Foundry) and `:518`
  (`?? "full"`, digigraph trace adapter).
- **Each retained claim holds:** `cli.enabled` (set by `local-cli.yaml:31-32`, strict
  schema, read by the CLI); `gate.showLanguageSelector` (reserved verbatim at
  `ARCHITECTURE.md:1428`, set by exactly 9 shipped configs, strict `GateSchema`);
  `layout` (validated at `embed-tenants.ts:391-392`, documented at `ARCHITECTURE.md:495`);
  `?layout=embed` (produced by `embed-popup-config.ts:110`, `widget.js:98`, the dashboard
  popup; no reader in `src/`; pinned by three tests); `gate.consumeUrl` (already absent
  from the client gate, server-only).
- **Doc consistency:** the plan doc's Phase 2b `activityDetail` gap is server-side and
  consistent; no contradiction with `apps/digichat/ARCHITECTURE.md`. Note the config table
  lives at `apps/digichat/ARCHITECTURE.md` (there is no `docs/digichat/ARCHITECTURE.md`).

## Post-fix verification (author session)

```
apps/digichat  npm run test   → 125 files / 1248 tests passed
apps/digichat  npm run lint   → 30 problems, 0 errors (all pre-existing warnings)
apps/digichat  npm run build  → TypeScript clean, all routes generated
python3 scripts/check_doc_links.py → check_doc_links: OK (418 markdown files scanned)
```

`packages/ui` was not touched by this change.
