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
| `run-activity.tsx`, `collapsible-root.tsx` | `elements/run-activity.tsx`, `elements/collapsible-root.tsx` at `assistant-ui/assistant-ui@1f41f916` (the `@assistant-ui/elements-run-activity` registry item, newer than the tag above; it uses only primitives the pinned package already has) |
| `surfaces.ts` | the `collapsePanel` class from `elements/surfaces.tsx` at the same commit (the only export Run activity uses) |

Import paths are rewritten. `run-activity.tsx` swaps `findLast` for an
equivalent `reverse().find()` (this package targets ES2022). Other local
changes, all in `tool-fallback.aui.tsx`:

- the argument and result blocks cap at `max-h-72` and scroll inside the
  card, so a long payload does not stretch the thread;
- `/view verbose` opens the cards (initial open state from `useViewDisclosure`).

The base thread (`../thread.tsx`) also uses assistant-ui's own working
indicator (the pulsing dot) and MessageError markup from the upstream
`elements/thread.aui.tsx`. The `digichat` skin keeps `../../stock/*`.

Consecutive reasoning and tool calls render as one Run activity disclosure
(`../elements/chain-of-thought-activity.tsx`): `MessagePrimitive.GroupedParts`
groups them under `group-chainOfThought`, the folded summary says what the
chain did ("Thought and used 2 tools"; "Thinking" / "Working" plus the latest
step while it runs), and expanding shows the reasoning and each tool call in
order. Reasoning and the tool-group wrappers are not rendered as their own
dropdowns inside it. `/view verbose` opens the chain on mount.
