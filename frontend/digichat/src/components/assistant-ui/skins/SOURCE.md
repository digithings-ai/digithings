# Official assistant-ui templates (11) + first-party `digichat`

Ids 1–11 match assistant-ui `list_templates`. `digichat` is the first-party
Thread (`@digithings/web/chat/thread`). Client containers pick one with
`chrome.skin` / `DIGICHAT_CHROME_SKIN` (fail closed). Baked YAML for each id
lives at `frontend/digichat/config/examples/skins/<id>.yaml` and is copied into
the image at `/app/config/examples/skins/`. Point `DIGICHAT_CONFIG_PATH` at
that file (or overlay `DIGICHAT_CHROME_SKIN`) and `/embed` + `POST /api/chat`
use it — `DIGICHAT_EMBED_TENANTS` is not required. Do not fetch
assistant-ui.com at request time.

| id | What mounts in the Next.js web container |
|---|---|
| `base` | Fixed Base demo Thread (`skins/base/thread.tsx`) |
| `chatgpt` | Vendored ChatGPT clone Thread |
| `claude` | Vendored Claude clone Thread |
| `grok` | Vendored Grok clone Thread |
| `gemini` | Vendored Gemini clone Thread |
| `perplexity` | Vendored Perplexity clone Thread |
| `react-ink` | Web facsimile of the Ink TTY demo. Original: `reference/.../react-ink` + `cli/` |
| `expo-react-native` | Phone-frame facsimile. Original: `reference/.../expo-react-native` |
| `base-assistant-ui` | Configurable Base: same Thread plus official `brandTheme` / labels shell |
| `webpage-assistant` | Docs layout + sidebar/modal Thread |
| `product-page-assistant` | Product dashboard + floating modal Thread |
| `digichat` | First-party Thread (digiweb tokens + primitives). Not a LAYOUT_SKINS owner. |

Downloads (fixed demos): `https://www.assistant-ui.com/api/xulux/demo-download?slug=<id>`
Expo: `https://github.com/assistant-ui/assistant-ui/tree/main/examples/with-expo`

Edits vs upstream for in-app mounts:

- import paths rewritten into this tree / stock markdown + tool fallback
- `CloneThreadShell` stripped (digichat owns thread-list via persistence)
- webpage / product-page use the parent `AssistantRuntimeProvider` (no nested demo runtime)
- Ink / Expo originals are not imported by Next.js
- `digichat` is owned source (`DigichatThread`), not a downloaded catalog template
