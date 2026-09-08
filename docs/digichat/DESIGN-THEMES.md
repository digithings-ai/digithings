# digichat design themes

The gallery iterates on the **official assistant-ui Thread**, themed with
digiweb CSS variables. It is not a restyle of a ChatGPT clone, and it is not
a second message tree.

## Gallery

Contract: [`frontend/digiweb/CHAT_THEME.md`](../../frontend/digiweb/CHAT_THEME.md).

Live: design-reference `/chatbot` (port 4013). Source of look: copied
`thread.aui.tsx` + shadcn token aliases onto `--bg` / `--ink` / `--accent`.

## Product skin: `digichat`

`chrome.skin: digichat` is the 12th id next to the 11 official catalog
templates. It consumes the gallery `/chatbot` look (`chatbot.css` + Thread
grammar). Catalog / third-party default remains `base`. First-party hosts
(digithings.ai / OCC) default unset `skin` to `digichat`. There is no third
custom theme — extra chrome.skin ids are not allowed.

```bash
DIGICHAT_CONFIG_PATH=/app/config/examples/skins/digichat.yaml
# or
DIGICHAT_CHROME_SKIN=digichat
```

## Catalog templates (untouched)

The 11 official assistant-ui ids (`base`, `chatgpt`, `claude`, `grok`,
`gemini`, `perplexity`, `react-ink`, `expo-react-native`, `base-assistant-ui`,
`webpage-assistant`, `product-page-assistant`) stay vendored clones. Do not
restyle them to look like digichat.

## Not in scope

- Using Ink / `@assistant-ui/react-ink` as a website or `/embed` look
- Porting CliThread / `session.css` back onto `/embed`
- Generating `design.md` from a client marketing-site scrape
- Digi product names in CamelCase — always lowercase in prose (`digichat`,
  `digigraph`, `digithings`, …)
