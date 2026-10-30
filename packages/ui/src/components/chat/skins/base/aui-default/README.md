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
| `collapsible-root.tsx` | `elements/collapsible-root.tsx` at `assistant-ui/assistant-ui@1f41f916` (the `@assistant-ui/elements-run-activity` registry item, newer than the tag above; it uses only primitives the pinned package already has) |
| `surfaces.ts` | the `collapsePanel` class from `elements/surfaces.tsx` at the same commit |

Import paths are rewritten. Local changes:

- `tool-fallback.aui.tsx`: the argument and result blocks cap at `max-h-72`
  and scroll inside the card, so a long payload does not stretch the thread;
  `/view verbose` opens the cards (initial open state from
  `useViewDisclosure`); the row's words and status come from the shared trace
  rules (`../../../trace-grouping/tool-row.ts`), and a running call's card
  shows its arguments, folding again once the call completes;
- `tool-group.aui.tsx`: `streamingOpen` (open while the group streams, folded
  on completion), as in the digichat skin's tool group.

The trace itself (`../elements/assistant-trace.aui.tsx`) is shared: the base
Thread and the stock Thread (`../../../stock/thread.aui.tsx`) both render it.

The base thread (`../thread.tsx`) also uses assistant-ui's own working
indicator (the pulsing dot) and MessageError markup from the upstream
`elements/thread.aui.tsx`. The `digichat` skin keeps `../../stock/*`.

The trace follows the digichat skin's grouping exactly
(`../../../trace-grouping`, shared with `gallery-thread/thread.aui.tsx`):
`MessagePrimitive.GroupedParts` puts consecutive reasoning and tool calls
under one work chain (`../elements/work-chain.tsx`), whose header is open
while the agent works and folds shortly after the answer starts (folded it
reads as the status line: "Working — web_search", "Used 3 tools"). Inside
it, adjacent reasoning is one reasoning box that opens and streams while it
runs, and adjacent tool calls are one `N tool calls` group that opens while
the tools run. Only the look differs from the digichat skin.
