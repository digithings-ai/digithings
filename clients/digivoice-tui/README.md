# digivoice-tui

OpenTUI setup shell for digivoice on the shared TUI foundation. Same labels as
`digivoice setup --print`: a left menu (Models, Features, Hotkeys, Hardware
recommendations, Review & save, Doctor, Quit) and one screen per item. Every
read is one `digivoice` run through `Bun.spawn` — `setup --json`, `doctor`,
`history --json`, `status`, `settings --json` — and an edit is `digivoice
settings set <key> <value>`. A refused or unreachable CLI stays an empty state.
The app does not invent a value. Speech stays local.

```bash
bun install
bun src/index.tsx                       # uses the `digivoice` console script
DIGIVOICE_BIN="python3 -m digivoice" PYTHONPATH=../digivoice/src bun src/index.tsx
```

The menu is focused on launch. `↑` `↓` moves. Enter selects a menu item, edits a
field, toggles a flag, or cycles a literal. `←` `→` cycle a literal. `Esc` goes
back. `h` opens History. `r` reloads. `q` quits. An edit is written with
`settings set` as you make it; the live status strip reads `digivoice status`.

The DIGIVOICE wordmark is the shared half-block mark
(`packages/ui/src/components/chat/digichat-wordmark`), the ASCII Magic
direction. `DIGIVOICE_WORDMARK_MS` freezes the scramble for screenshots and for
reduced motion. One font config: Geist Mono. This app is bun-managed and lives
outside the root npm workspaces.
