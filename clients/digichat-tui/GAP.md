# digichat web thread vs OpenTUI

Compared with the digichat thread in `packages/ui` (`DigichatThread`, `DigichatThreadList`, the gallery composer, and the product slash palette in `packages/digichat-ui`). The desk page mounts that same thread. Reads stay on the official chat routes. A down service, a 502, or a 503 still paints no sessions and no messages.

| Item | Web | Terminal | Status |
| --- | --- | --- | --- |
| Boot sweep | Cube outline sweeps the composer until the shell is ready | Braille spinner plus `Loading conversation` for as long as the first read is in flight. No extra delay after the read returns | Closed. A 5×5 cube field cannot be drawn in one cell |
| History skeleton | Shimmering user blocks and assistant lines while history loads | Shade bars in that same arrangement, under the loading line | Closed |
| Working indicator | `loading` cubes, plus Connecting… / Warming up… from the stream | Spinner and `Assistant is working` while a send is in flight. Stop is `■` | Closed for the spinner. Connecting / Warming up need a stream this route does not return, so those words stay absent |
| Welcome | Bottom-aligned headline, typed in, only on a settled empty thread | Same headline, block caret while it types, same placement | Closed |
| Welcome body | Static lines from deploy config | Shown only when a body is provided. This mount has none | Closed |
| Example prompts | Diamond mark plus the prompt, only from config or the runtime | Same mark when prompts exist. None are invented | Closed |
| Follow-up chips | Runtime suggestions after a reply | Not drawn when the payload has none | Closed |
| Session rail | `digichat` and a new-chat cube on one header row. Titles only. Active row filled. Empty title falls back to `new chat` | Same header, `+` for the cube, fill on the active row, `new chat` only for a blank title that actually arrived | Closed. The inverse-plus cube is a plus |
| Empty rail | No fake conversations | No fake conversations | Closed |
| User turn | `>` cube, left aligned, no bubble | `>` and the text | Closed |
| Assistant turn | No role arrow. Text left aligned | Indented text, no arrow | Closed |
| Tool row | Collapsed name, cube while running, detail on open | `>` / `v` plus the name, spinner while status is `running`, detail when open (`o`) | Closed. The payload has one detail string, not separate args and result slabs |
| Reasoning | Collapsed `Reasoning` row | Same row when the payload includes reasoning | Closed |
| Action bar | Copy, redo, more (export) on the last assistant turn. Hidden while running | `copy  redo  more` on that turn. `c` / `r` / `m` | Closed |
| Edit | Edit composer on the last user turn | `edit` loads that text. `e`. This route appends, it does not replace | Closed, with that limit on the status line |
| Branch picker | Hidden when there is one branch. Undo only when a previous branch exists | Hidden. `/undo` says `one branch` | Closed |
| Feedback | Thumbs only when feedback is enabled. Default off | Not shown | Closed |
| Message error | Danger banner, API text, Retry | `!` plus the failure, and `retry`. `r` resends the last user turn, or reloads the read when the screen itself failed | Closed |
| 502 / 503 | Empty thread, server message, no welcome | Same. Welcome stays off | Closed |
| Other HTTP errors | Error, no invented thread | Same | Closed |
| Unreachable API | The read fails | `the official API could not be reached.` | Closed |
| Timestamps | Token and duration timing on the action bar | The `at` field is shown when the payload has it. Token counts are not in this payload | Closed for `at`. Tokens are absent because the route does not send them |
| Markdown | Headings, tables, fenced code, a copy cube on the fence | Wrapped plain text. Thread copy and export still carry the text | Terminal limit. Cells do not render a styled table or a per-fence button |
| Citations | Source rows when the part exists | Not in this payload, so not drawn | Closed |
| Scroll to bottom | Cube button once the viewport leaves the end | `↓ Scroll to bottom` after page up. `b` or End returns | Closed |
| Composer | Bordered field, placeholder `Ask digichat…`, block caret, Enter sends | Same placeholder, blinking block, Enter sends | Closed |
| Attach | Plus cube, chips `name · file`, remove cube. Files reach the model | `+` (Tab, then Enter, or `a`). Chip is `name · file  x`. Backspace on an empty draft removes it | The chip is kept. This route accepts `{ text }` only, so a send says the attachment was not uploaded. No drag-and-drop and no image lightbox |
| Voice | Mic cube, then a stop cube while dictating | `mic` on the tray. Enter on it says voice input is not available | Terminal limit. There is no Web Speech API here. The control stays |
| Send / stop | Send cubes, brighter when text is present. Stop cubes while running | `↑` mute or brighter. `■` aborts the request | Closed |
| Credit | Centered `powered by digichat — a digithings product.` with a link on digithings | The same sentence, centered, always | The link is not clickable in this cell. The words match |
| Slash palette | Flat list above the composer: label and hint, highlight, empty state `No matching commands`. Opens on `/` | Same list, same empty line, same placement. Up/down, Enter, Escape | Closed |
| Configure commands | Toggles, choices, and panes for search, view, thinking, language, effort, provider, models, MCP, tools, sessions, new, clear, compact, undo, redo, copy, export, help | Same commands. Toggles and choices update a local session. `/settings` opens that list | Local only. This route has no force-tool or prefs headers, so a query is sent as text and the status says so |
| Language rows | Featured `/english` … `/french` plus the choice list | Those five rows and the choice list | The long ISO picker is a separate web menu. The slash list is these five |
| Models | Model list from the deployment | `No models returned.` | Closed. None are invented |
| Provider | Provider catalog and a key field | openrouter, openai, anthropic, gemini, xai. The key row says keys are not entered | Secrets are not read or printed. This route cannot take a key |
| MCP | Server list, JSON, OAuth | `No MCP servers.` and `new`, which says OAuth needs a browser | Terminal limit for the browser handoff. No servers are invented |
| Tools | Connected catalog | `No connected tools.` Names that already arrived on a tool row show up in `@` | Closed |
| Mentions | `@` list, or `No matching tools` | Same | Closed |
| Help | The slash list is the help | `/` and `?` show that list | Closed |
| Copy | Clipboard, check cube | Status `copied` and OSC 52 | A terminal may ignore OSC 52. The text is not printed |
| Export | Downloads `digichat.md` as `## You` / `## digichat` | Same markdown in the thread column. Tool rows are omitted, as on the web | No browser download dialog |
| Compact | Summarizes the thread | `compact is not available on this route` | Closed. No summary is invented |
| New chat | Header cube, `/new`, `/clear` | Header `+`, `n`, `/new`, `/clear` create a session through the route | Closed |
| Desk read strip | Three diagnostic blocks under the desk page only | Not part of the digichat thread, so not drawn | Closed. The routes are still the ones the thread reads |

Keyboard when the composer is idle: `j`/`k` sessions, `n` new, `i` or Enter compose, `/` palette, `a` attach, `c` copy, `r` redo or retry, `m` more, `e` edit, `o` open a tool or reasoning row, `s` settings, `?` help, `b` bottom, `q` quit. Tab arms attach, mic, and send.
