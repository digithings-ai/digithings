# digivoice setup: `--print` / legacy TUI vs OpenTUI

digivoice is TUI-first: there is no web app to compare against, so this table
compares the terminal shell to the two things that came before it — the
`digivoice setup --print` / `setup --json` surface (the canonical mock in
`digivoice/mocks/cli-setup-wizard.md`, CHR-860 / #4953) and the legacy
`digivoice/tui` screen (develop only). The OpenTUI shell reads the same CLI; it
does not re-implement speech.

| Item | `setup --print` / legacy | Terminal | Status |
|------|--------------------------|----------|--------|
| Setup menu (7 items) | printed list | left rail, arrow + Enter | Closed |
| Models screen | dotted field list | card + Edit/Toggle rows | Closed |
| Features screen | dotted field list | card + Toggle/Cycle rows | Closed |
| Hotkeys (read-only) | printed docs | card, read-only | Closed |
| Hardware recommendations | stub pointer (#4939) | tier list + pointer | Closed, stub like the CLI |
| Review & save | settings dump | all settings dotted | Closed |
| Doctor | `[ok]/[missing]/[info]` text | toned check rows + `result:` | Closed |
| History | `history --json` / `--last N` | `h`, toned entries | Closed, reached by key |
| Live status | `status` snapshot | status strip, polled | Closed |
| Field edit | `settings set k v` | inline edit, saved on Enter | Closed |
| Flag toggle / literal cycle | `settings set k v` | Enter/Space toggle, ←→ cycle | Closed |
| DIGIVOICE wordmark | legacy pixel hero | shared half-block mark | Closed |
| System / Logs screens | legacy TUI screens | not built | Parked |
| Update / Uninstall | thin CLI stubs | not built | Terminal limit: the CLI prints a stub |
| dict / speak live take | CLI commands | not driven from the shell | Parked: a take is a CLI command, not a screen |
| Web app | none | none | TUI-first by design |

Keyboard: `↑` `↓` move, Enter acts, `←` `→` cycle, `Esc` back, `h` history,
`r` reload, `q` quit.
