# assistant-ui default trace parts (base skin)

Copies of assistant-ui's own Reasoning, ToolGroup and ToolFallback components
at the pinned `@assistant-ui/react@0.15.18` tag
(`assistant-ui/assistant-ui@d511ff49`, `packages/ui/src/components/react/assistant-ui/elements/`,
the source of the `https://r.assistant-ui.com/base/*` registry items), so the
`base` / `base-assistant-ui` skins render reasoning, tool calls and tool
groups exactly as assistant-ui ships them (no digichat trace styling).

| file | upstream file at the tag |
|---|---|
| `reasoning.tsx`, `reasoning.aui.tsx` | `elements/reasoning.tsx`, `elements/reasoning.aui.tsx` |
| `tool-group.aui.tsx` | `elements/tool-group.aui.tsx` |
| `tool-fallback.aui.tsx` | `elements/tool-fallback.aui.tsx` (name, arguments, result, approval controls, duration) |
| `collapsible.tsx` | shadcn base-nova `ui/collapsible.tsx` (base-ui) |

Import paths are rewritten. Local changes, all in `tool-fallback.aui.tsx`:

- the argument and result blocks cap at `max-h-72` and scroll inside the
  card, so a long payload does not stretch the thread;
- `/view verbose` opens the cards (initial open state from `useViewDisclosure`).

The base thread (`../thread.tsx`) also uses assistant-ui's own working
indicator (the pulsing dot) and MessageError markup from the upstream
`elements/thread.aui.tsx`. The `digichat` skin keeps `../../stock/*`.
