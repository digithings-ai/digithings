# #4954 craft pass — DigiVoice setup TUI (HOLD Merge)

Chris visual: NOT Claude-Code / OpenClaw quality yet. Fix on worktree
`/Users/chrisstefan/Code/digithings-wt-4953-cli-setup` branch `task/4953-digivoice-cli-setup`.

## Must
1. **Redraw in place** — no duplicated menu lines as you navigate. Full-screen or
   alternate buffer + clear + redraw each key; never scroll-append menus.
2. **DigiThings / DigiVoice logo header** matching digithings.ai PixelWordmark look
   (pixel block ASCII / braille wordmark — simple, not a web UI). Title: DigiVoice setup.
3. **Full CLI nav**: ↑↓ highlight, Enter select, Space toggle multi where relevant,
   Esc back, q quit; clear formatting (inverse/bold highlight, no scrap lines).
4. Keep setup + doctor + settings spine; `--print` / noninteractive unchanged for agents.

## Out
No Merge until Chris OK after craft. No new heavy deps if stdlib ANSI is enough;
prompt_toolkit/textual only if Muse judges stdlib insufficient — prefer stdlib first.

## Done bar
- OpenCode Muse implement + tests still green
- Push tip on #4954
- Re-hatch if tip moved
- Re-open Terminal `digivoice setup` for Chris
- Ping One: tip SHA + how to re-run
