# CHR-858 / Fixes #4947 — DigiVoice banner UX v5.8 SHIP

Chris locked mock look **2026-10-01 ~20:39 Rome**. Implement product PR now (HOLD lifted).

## SoT mock
`/workspace/digivoice-banner-ux-v5.8-mock.html` (also Chris Desktop + `~/Library/Application Support/digivoice/mocks/banner-ux-v5.8.html` if present)

## Product base
`origin/develop` after #4937 banner+Esc. Open AGENTS.md + digivoice AGENTS.md first. Branch off develop. PR → develop with `Fixes #4947`.

## Locked behavior (implement all)

### From issue #4947 / CHR-858
- Remove ~60s hard record cap; ~10s silence → pause (not force-finish)
- Density setting: `mini` | `peek` (default) | `full`
- Peek auto-hides after idle; full stays; mini = StatusGrid only
- Position setting / disable banner still works (CLI settings)
- DigiChat StatusGrid squares (not dots); no DigiVoice/Recording/Esc chrome copy
- Esc = full discard (no paste/blank/history)

### v5 visual + interaction (from mock + Chris locks)
- StatusGrid always top-left; hug content (no empty gutter/min-width stretch)
- Equal padding mini/peek/full; light/dark DigiChat flips (RYG status colors stay)
- No settings UI on banner — CLI owns config
- Hover: icon-only controls **below** banner (copy + × hide); stack if mini, horizontal right-aligned if wider; equal viewport edge inset
- Banner hidden by default; spawn via CLI/hotkey (no dictation required to show)
- Drag free; snap near 9 anchors; persist position
- Click banner = expand/collapse density (no dedicated expand button)
- Typewriter slightly faster; peek→full continues caret (no restart); close/collapse = **instant hide** (no reverse typewriter)
- Full transcript ≤ ~50vh, scrollable, **scrollbar hidden**
- Uniform line widths; first line locks final banner width so later lines don’t stretch mid-type
- Center pin keeps center on expand; edge pins grow outward

## Out of scope
- #4939 hardware catalog
- Speak-selection grab
- CLI setup TUI mock (next after this lands)

## Done bar
1. PR open `Fixes #4947` → develop
2. In-session review hatch `<!-- in-session-review -->` + `reviewed:agent`
3. Ping One / Merge when green — then Mac Hammerspoon Reload Config for Chris smoke
4. Clean OpenCode sessions when done

OpenCode free ladder; parallel sessions OK keep winner. lowercase digi*.
