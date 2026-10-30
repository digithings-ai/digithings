# assistant-ui default trace parts (base skin)

Unmodified copies of assistant-ui's own Reasoning, ToolGroup and ToolFallback
components, so the `base` / `base-assistant-ui` skins render reasoning and tool
calls exactly as assistant-ui ships them (no digichat trace styling).

| file | source (in `apps/digichat/reference/assistant-ui-templates/`) |
|---|---|
| `reasoning.tsx`, `reasoning.aui.tsx` | `base/components/assistant-ui/elements/` |
| `tool-group.aui.tsx` | `base/components/assistant-ui/elements/` |
| `tool-fallback.aui.tsx` | `product-page-assistant/components/assistant-ui/tool-fallback.tsx` (registry ToolFallback: name, arguments, result, collapsible) |
| `collapsible.tsx` | `base/components/ui/collapsible.tsx` (base-ui) |
| `collapsible-radix.tsx` | `product-page-assistant/components/ui/collapsible.tsx` (radix) |

Only import paths are rewritten. The `digichat` skin keeps `../../stock/*`.
A tool call that waits on a human approval still uses the stock fallback,
which owns the approval controls.

Local change: the ToolFallback argument and result blocks cap at `max-h-72`
and scroll inside the card, so a long payload does not stretch the thread.
