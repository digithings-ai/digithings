# digiquant app — keyboard shortcuts

The digiquant app is the Brief desk, served at **`/app`** on digiquant.io
(`/app/brief` redirects to `/app`). The old terminal app (`apps/digiquant-app`)
is retired; only its keyboard map was carried over (owner decision 2026-10-11).

Source of truth: `apps/digiquant-web/components/desk/shortcuts.ts`. Press `?`
anywhere in the app to see this list. Keys match the digiquant TUI
(`clients/digiquant-tui/src/app.tsx`) where the TUI has the same action.

| Keys | Action | TUI |
|---|---|---|
| `/` or `⌘K` | Go to any page (command line) | `/` |
| `↑ ↓ Enter` | Move / open in the command list | same |
| `d` | Switch desk (locked desks show what unlocks them) | `d` |
| `n` | Focus the page rail (opens the drawer on a phone) | — |
| rail `↑ ↓` / `j k` | Walk the page tree; `Enter` loads the page | `↑ ↓` / `j k` |
| rail `→ ←` / `l h` | Open / close a folder, step in or back to the parent | `→ ←` / `l h` |
| `Home` / `End` | First / last page in the rail | — |
| `[` `]` | Narrower / wider page rail | `[` `]` |
| `Tab` | Move between blocks and controls | `Tab` |
| `Esc` | Close menu, list, drawer or this help | `Esc` |
| `?` | Show / hide shortcuts | — |

Not carried over (owner ruling 2026-10-12): the old app's `e` layout-edit
mode, its drag-to-resize sidebar, and `[`/`]` pin-and-unpin — the desk has
no editable layout, and `[` `]` now narrows and widens the page rail.
`Tab` moves between focusable blocks in DOM order (owner ruling 2026-10-12
make_it_work). `q` (quit) is TUI-only.
