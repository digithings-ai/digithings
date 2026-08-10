/**
 * Step caret — the house type-out, applied to waiting. The running step's label
 * types out at the blinking block cursor, holds, deletes, and the next follows.
 *
 * PROMOTED to `@digithings/web`; consume it from there. The implementation and
 * the full docblock live in `web/src/components/terminal/TerminalStepCaret.tsx`,
 * and the `.tl-*` styles in `@digithings/web/styles/terminal-loaders.css`. This
 * file stays as the re-export so the specimen keeps a stable import path while
 * there is exactly one implementation to drift from.
 */
export { TerminalStepCaret, type TerminalStepCaretProps } from "@digithings/web";
