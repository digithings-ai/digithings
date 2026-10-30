# Stock assistant-ui (baseline preview)

Copies of the public assistant-ui **base** registry (`https://r.assistant-ui.com/base/…`)
plus the matching shadcn **base-nova** primitives those files import
(button, tooltip, collapsible, dialog, avatar, skeleton, textarea).

The only edits here are:

- import paths rewritten to this folder
- `dialog.tsx` close icon uses `lucide-react` `XIcon` instead of their
  registry `IconPlaceholder` (that module is not in this app)
- `tool-fallback.aui.tsx` adds the Gloomberb attribution footer
  (`ToolFallbackAttribution`, reading `readGloomberbAttribution` from
  `@digithings/ui`) under the Result pane — the same line the first-party
  gallery thread renders (#4098). No other styling changes.

## Shape: the base skin's radii

Inside the stock Thread every corner follows the base skin (assistant-ui's
base registry, `https://r.assistant-ui.com/base/*.json`, deps
`@assistant-ui/react@^0.15.32`, and shadcn **base-nova**,
`https://ui.shadcn.com/r/styles/base-nova/*.json`): `--composer-radius: 1.5rem`
(composer and user bubble, the base skin's `--radius-thread`), `rounded-full` composer buttons and
scroll-to-bottom, `rounded-xl` more-menu / dialog / code block, `rounded-lg`
menu items, reasoning and tool-group, `rounded-md` suggestions, notices and
tooltips, base-nova button sizes. Never put a zero-radius shell back.

Some of these files (button, tooltip, textarea, markdown, notices, tool
fallback, reasoning, tool group, JSON view) are also used by other skins, which
keep their own square house radius. They read `useStockShape()` from
`stock-shape.tsx`; `StockShapeProvider` wraps the stock `Thread`, so only the
stock skin gets the rounded shapes. Pinned by `thread-defaults.source.test.ts`,
`stock-more-menu.source.test.ts` and `stock-shape.render.test.tsx`.

Host components passed through the Thread's `components` prop (`Welcome`,
`Footer`, `AssistantMessage`, `ToolFallback`, `ToolGroup`, `ReasoningGroup`)
render inside `StockShapeProvider` too, so any of these shared files they use
round the same way. Portals opened outside the provider (and every other
skin) keep the square default: the context defaults to `false`.

## Colour: the raised surface

The stock parts paint their raised fill (user bubble, table heads, skeletons,
dialog, inline code, hovers) with `bg-surface-2`. The theme bridge
(`styles/chat-aui.css`) declares `--color-surface-2`, switched on only on a
page that holds a stock thread (`html:has([data-stock-thread])`). Other skins
reuse some stock parts (markdown, tool cards) and keep them transparent.

## Trace: the base skin's work chain

The stock Thread draws reasoning and tool calls with the base skin's trace
(`../skins/base/elements/assistant-trace.aui.tsx`, shared with the base
Thread): one collapsible work chain per turn ("Working" / "Worked", folded
"Used 3 tools"), a collapsible reasoning box and `N tool calls` group inside
it, and assistant-ui's own collapsible tool card (arguments, result) for each
call. Grouping and fold rules are `../trace-grouping`; the parts are
`../skins/base/aui-default` (see its README). Text, files, images and the
loading indicator stay the stock ones. A host's `ToolFallback`, `ToolGroup`
or `ReasoningGroup` still replaces the matching piece.

Do not restyle these files for digichat. `/baseline` mounts this Thread with no extra chrome.

Full elements catalog (what else exists upstream and how to attach it):
[`packages/ui/ASSISTANT_UI_ELEMENTS.md`](../../../../../../packages/ui/ASSISTANT_UI_ELEMENTS.md).

## License

The assistant-ui registry files are copied from
[assistant-ui/assistant-ui](https://github.com/assistant-ui/assistant-ui)
(MIT License, Copyright (c) 2025 AgentbaseAI Inc.) and the base-nova
primitives from [shadcn-ui/ui](https://github.com/shadcn-ui/ui) (MIT License,
Copyright (c) 2023 shadcn); both notices apply to the vendored files here.
