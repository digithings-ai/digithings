# assistant-ui official template sources

Full starter copies of the 11 catalog templates, for client forks (colors,
copy, extra pages). The Next.js app mounts the rewritten skins under
`src/components/assistant-ui/skins/` — it does not compile these trees.

| directory | template id | source |
|---|---|---|
| `base/` | `base` | xulux `demo-download?slug=base` |
| `chatgpt` … `perplexity` | clones | already in `src/components/assistant-ui/skins/*.tsx` |
| `react-ink/` | `react-ink` | xulux `demo-download?slug=react-ink` |
| `expo-react-native/` | `expo-react-native` | GitHub `examples/with-expo` |
| `base-assistant-ui/` | `base-assistant-ui` | hosted configurable Base download |
| `webpage-assistant/` | `webpage-assistant` | hosted template download |
| `product-page-assistant/` | `product-page-assistant` | hosted template download |

Logs / `tsconfig.tsbuildinfo` from the hosted zips are stripped.
