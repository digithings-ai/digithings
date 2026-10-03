# CHR-860 / Fixes #4953 — DigiVoice CLI setup + doctor + config spine

## Locks (Chris / One 2026-10-01)
- DigiVoice CLI = **only** config surface besides live banner (no settings web UI).
- Shape like Claude Code / Grok CLI: `digivoice` launches local terminal config app.
- `digivoice setup` — interactive arrow-key menus, enter to select, walk every preference.
- `digivoice doctor` — verify config + health (models, hotkeys, HS adapter, audio).
- Commands: settings, STT/TTS/rewrite models, hotkeys docs, history browse/search/copy-last, update, uninstall stubs OK if not fully wired.
- Hardware-aware model tiers: **hook + docs** for #4939 / CHR-853; do not rebuild full catalog epic in this PR.
- Pixel language: DigiVoice banner / digithings.ai top bar + DigiChat-flat — keep simple (CLI text/TUI, not a web mock required for first PR if TUI ships).
- OpenCode-only implement. No Bot cloud. No secrets in Muse prompts.

## First PR bar (this seat)
1. Working interactive `digivoice setup` (arrow/enter wizard over existing VoiceSettings knobs).
2. Strengthened `digivoice doctor` (config validity + models + hotkeys docs + HS adapter presence + audio tools) with clear pass/fail.
3. Settings get/set/path remain solid; `setup` is real wizard (not just alias that prints settings).
4. Stubs or thin commands for `update` / `uninstall` if easy; history already exists — improve browse if cheap.
5. Docs: digivoice README + AGENTS how agents drive setup.
6. Tests under tests/dvo for setup/doctor non-interactive paths (TTY mock or `--non-interactive` / env).
7. PR → develop with **Fixes #4953**, hatch `<!-- in-session-review -->` + `reviewed:agent`.

## Worktree
`/Users/chrisstefan/Code/digithings-wt-4953-cli-setup` branch `task/4953-digivoice-cli-setup`

## Baseline
Prefer tip that includes DigiVoice banner v5.8 (#4950) + develop. Rebase/merge github develop if Origin tip lags.

## Out of scope
Settings web UI; banner chrome; full model download catalog (#4939 children).

## Branch (One lock)
`task/digivoice-cli-setup` (not task/4953-…). PR Fixes #4953.

## Sequence
1. **CLI setup mock first** (text/HTML or ANSI mock of setup wizard flow — Desktop or digivoice/mocks OK; do not block ship on fancy mock)
2. Then OpenCode implement
