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

## Shape: assistant-ui's default radii

Inside the stock Thread every corner follows assistant-ui's defaults, matched
against the base registry (`https://r.assistant-ui.com/base/*.json`, deps
`@assistant-ui/react@^0.15.32`) and shadcn **base-nova**
(`https://ui.shadcn.com/r/styles/base-nova/*.json`): `--composer-radius: 1rem`
(composer and user bubble), `rounded-full` composer buttons and
scroll-to-bottom, `rounded-xl` more-menu / dialog / code block, `rounded-lg`
menu items, reasoning and tool-group, `rounded-md` suggestions, notices and
tooltips, base-nova button sizes. Never put a zero-radius shell back.

Some of these files (button, tooltip, textarea, markdown, notices, tool
fallback, reasoning, tool group, JSON view) are also used by other skins, which
keep their own square house radius. They read `useStockShape()` from
`stock-shape.tsx`; `StockShapeProvider` wraps the stock `Thread`, so only the
stock skin gets the rounded shapes. Pinned by `thread-defaults.source.test.ts`,
`stock-more-menu.source.test.ts` and `stock-shape.render.test.tsx`.

Do not restyle these files for digichat. `/baseline` mounts this Thread with no extra chrome.

Full elements catalog (what else exists upstream and how to attach it):
[`packages/ui/ASSISTANT_UI_ELEMENTS.md`](../../../../../../packages/ui/ASSISTANT_UI_ELEMENTS.md).
