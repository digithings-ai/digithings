/** Drop Tailwind-only at-rules so a replay file can host the chat sheets raw. */

export function stripStylesheet(css: string): string {
  const withoutImport = css
    .replace(/@import\s+[^;]+;/g, "")
    .replace(/@custom-variant\s+[^\n]+/g, "")
    .replace(/@source\s+[^;]+;/g, "");
  return stripBalanced(withoutImport, "@theme");
}

function stripBalanced(css: string, keyword: string): string {
  let out = "";
  let cursor = 0;
  while (cursor < css.length) {
    const at = css.indexOf(keyword, cursor);
    if (at === -1) {
      out += css.slice(cursor);
      break;
    }
    out += css.slice(cursor, at);
    const open = css.indexOf("{", at);
    if (open === -1) break;
    let depth = 0;
    let end = open;
    for (; end < css.length; end += 1) {
      const char = css[end];
      if (char === "{") depth += 1;
      else if (char === "}") {
        depth -= 1;
        if (depth === 0) {
          end += 1;
          break;
        }
      }
    }
    cursor = end;
  }
  return out;
}

/** Layout the live thread gets from Tailwind, plus the replay player chrome. */
export const REPLAY_SHELL_CSS = `
html, body { margin: 0; height: 100%; }
body {
  background: var(--bg, #0a0e0c);
  color: var(--ink, #eceef0);
}
.replay-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem 0.9rem;
  padding: 0.45rem 0.8rem;
  border-bottom: 1px solid var(--hair, rgba(255,255,255,0.09));
  background: var(--surface, #121417);
  color: var(--ink-mute, #6b7177);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.72rem;
  position: sticky;
  top: 0;
  z-index: 2;
}
.replay-bar button, .replay-bar select {
  font: inherit;
  color: var(--ink, #eceef0);
  background: transparent;
  border: 1px solid var(--hair, rgba(255,255,255,0.09));
  padding: 0.15rem 0.45rem;
  cursor: pointer;
}
.replay-bar .replay-keys { margin-left: auto; }
.replay-stage {
  min-height: calc(100% - 2.4rem);
  display: flex;
  flex-direction: column;
}
.replay-scroll {
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
}
.replay-column {
  width: min(100%, var(--thread-max-width, 44rem));
  margin: 0 auto;
  padding: 1rem 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  box-sizing: border-box;
}
.replay-thread [data-slot="aui_message-group"] {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
.replay-thread [data-slot="aui_user-message-root"],
.replay-thread [data-slot="aui_assistant-message-root"] {
  display: grid;
  grid-template-columns: 1.25rem minmax(0, 1fr);
  column-gap: 0.55rem;
  align-items: start;
}
.replay-thread [data-slot="aui_assistant-message-root"] {
  grid-template-columns: minmax(0, 1fr);
}
.replay-matrix {
  display: inline-block;
  width: 0.875rem;
  height: 0.875rem;
  color: inherit;
}
.replay-thread .aui-msg-marker {
  display: inline-flex;
  width: 1.25rem;
  margin-top: 0.2rem;
  color: var(--ink);
}
.replay-thread [data-slot="aui_work-chain-trigger"],
.replay-thread [data-slot="tool-fallback-trigger"],
.replay-thread [data-slot="reasoning-trigger"] {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  width: fit-content;
  border: 0;
  background: transparent;
  color: var(--ink-mute);
  font: inherit;
  text-align: start;
  padding: 0.15rem 0;
}
.replay-thread summary { list-style: none; }
.replay-thread summary::-webkit-details-marker { display: none; }
.replay-thread details[open] > summary > [data-slot="disclosure-chevron"] [data-slot="dot-matrix-grid"] {
  transform: rotate(90deg);
}
.replay-thread [data-slot="aui_work-chain-content"],
.replay-thread [data-slot="tool-fallback-content"],
.replay-thread [data-slot="reasoning-content"] {
  padding-left: 1.15rem;
}
.replay-thread .aui-reasoning-text {
  white-space: pre-wrap;
  color: var(--ink-mute);
  font-size: 0.82rem;
  line-height: 1.45;
}
.replay-footer {
  margin-top: auto;
  padding-top: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.replay-thread [data-slot="aui_composer-shell"] {
  border: 1px solid var(--hair);
  background: var(--composer-bg, var(--surface));
  padding: var(--composer-padding, 0.5rem);
}
.replay-thread .aui-composer-input {
  width: 100%;
  border: 0;
  resize: none;
  background: transparent;
  box-sizing: border-box;
}
.replay-thread .aui-thread-welcome-suggestion {
  display: grid;
  grid-template-columns: 1.25rem minmax(0, 1fr);
  gap: 0.55rem;
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
  padding: 0.12rem 0;
}
.replay-caret {
  display: inline-block;
  width: 0.48em;
  height: 1em;
  margin-left: 0.12em;
  vertical-align: -0.12em;
  background: var(--ink);
}
[data-replay-turn][hidden] { display: none !important; }
.replay-thread .aui-md-table { border-collapse: collapse; font-size: 0.82rem; }
.replay-thread .aui-md-table th, .replay-thread .aui-md-table td {
  border: 1px solid var(--hair);
  padding: 0.25rem 0.45rem;
  text-align: start;
}
`;
