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

Do not restyle these files for digichat. `/baseline` mounts this Thread with no extra chrome.

Full elements catalog (what else exists upstream and how to attach it):
[`packages/ui/ASSISTANT_UI_ELEMENTS.md`](../../../../../../packages/ui/ASSISTANT_UI_ELEMENTS.md).
