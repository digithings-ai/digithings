/**
 * One self-contained HTML document. Stylesheets and fonts are passed in
 * already inlined; the transcript uses the live digichat class hooks.
 */

import { PALETTE_IDS } from "../theme/palette-registry";
import { escapeHtml } from "./escape";
import { replayFilename } from "./filename";
import { disclosureChevron, dotMatrix } from "./icons";
import { renderMarkdown } from "./markdown";
import { replayPlayerScript } from "./player";
import type {
  ReplayBlock,
  ReplayChainItem,
  ReplayDocument,
  ReplayTool,
  ReplayTurn,
} from "./types";

export function buildReplayHtml(doc: ReplayDocument, css: string): string {
  const theme = doc.theme.resolved === "light" ? "light" : "dark";
  const palette =
    doc.theme.palette !== "default" && (PALETTE_IDS as readonly string[]).includes(doc.theme.palette)
      ? doc.theme.palette
      : "";
  const paletteAttr = palette ? ` data-palette="${escapeHtml(palette)}"` : "";
  const accent = doc.accent
    ? ` style="--accent:${escapeHtml(doc.accent.color)};--accent-foreground:${escapeHtml(doc.accent.foreground)}"`
    : "";
  const open = doc.theme.view === "verbose" ? " open" : "";
  const title = escapeHtml(doc.title || doc.deployment || "digichat");
  return `<!DOCTYPE html>
<html lang="en" data-theme="${theme}"${paletteAttr} class="${theme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>${title}</title>
<style>
${css}
</style>
</head>
<body>
${renderBar(doc)}
<div id="replay" class="replay-stage" data-mode="full" data-revealed="${doc.turns.length}" data-view="${escapeHtml(doc.theme.view)}" data-speed="1" data-deployment="${escapeHtml(doc.deployment)}">
  <div id="replay-scroll" class="replay-scroll">
    <div data-thread-skin="digichat" class="digichat-thread replay-thread"${accent}>
      <div class="replay-column">
        ${renderWelcome(doc)}
        <div data-slot="aui_message-group">
          ${doc.turns.map((turn) => renderTurn(turn, open)).join("")}
        </div>
        ${renderFooter(doc)}
      </div>
    </div>
  </div>
</div>
<script>
${replayPlayerScript()}
</script>
</body>
</html>
`;
}

export function replayDownloadName(doc: ReplayDocument): string {
  return replayFilename(doc.deployment, doc.exportedAt);
}

function renderBar(doc: ReplayDocument): string {
  const themeValue = `${doc.theme.palette === "default" ? "default" : doc.theme.palette}|${doc.theme.resolved}`;
  const options = [
    `<option value="default|dark"${themeValue === "default|dark" ? " selected" : ""}>Default dark</option>`,
    `<option value="default|light"${themeValue === "default|light" ? " selected" : ""}>Default light</option>`,
  ];
  for (const id of PALETTE_IDS) {
    for (const mode of ["dark", "light"] as const) {
      const value = `${id}|${mode}`;
      const label = `${id} ${mode}`;
      options.push(
        `<option value="${escapeHtml(value)}"${value === themeValue ? " selected" : ""}>${escapeHtml(label)}</option>`,
      );
    }
  }
  const views = (["quiet", "balanced", "verbose"] as const)
    .map(
      (view) =>
        `<option value="${view}"${doc.theme.view === view ? " selected" : ""}>${view}</option>`,
    )
    .join("");
  return `<div class="replay-bar">
  <button type="button" id="replay-play">Play</button>
  <button type="button" id="replay-full">Transcript</button>
  <label>Speed <select id="replay-speed" aria-label="Playback speed">
    <option value="0.5">0.5×</option>
    <option value="1" selected>1×</option>
    <option value="2">2×</option>
    <option value="4">4×</option>
  </select></label>
  <label>Theme <select id="replay-theme" aria-label="Theme">${options.join("")}</select></label>
  <label>View <select id="replay-view" aria-label="View">${views}</select></label>
  <span class="replay-keys">← previous turn · → next turn · space play</span>
</div>`;
}

function renderWelcome(doc: ReplayDocument): string {
  if (!doc.welcome && doc.welcomeBody.length === 0) return "";
  const body = doc.welcomeBody
    .map((line) => `<p class="aui-thread-welcome-copy">${escapeHtml(line)}</p>`)
    .join("");
  return `<header data-slot="aui_thread-welcome" class="aui-thread-welcome-root">
  ${doc.welcome ? `<h1 class="aui-thread-welcome-message-inner">${escapeHtml(doc.welcome)}</h1>` : ""}
  ${body}
</header>`;
}

function renderFooter(doc: ReplayDocument): string {
  const suggestions = doc.suggestions
    .map(
      (prompt) => `<button type="button" class="aui-thread-welcome-suggestion">
        <span class="aui-msg-marker" aria-hidden="true">${dotMatrix("example", { decorative: true })}</span>
        <span>${escapeHtml(prompt)}</span>
      </button>`,
    )
    .join("");
  return `<footer class="replay-footer aui-thread-viewport-footer">
  ${suggestions ? `<div class="aui-thread-welcome-suggestions">${suggestions}</div>` : ""}
  <form data-slot="aui_composer-shell" class="aui-composer-root" onsubmit="return false">
    <textarea class="aui-composer-input" readonly rows="1" aria-label="Message" placeholder="${escapeHtml(doc.placeholder)}"></textarea>
  </form>
</footer>`;
}

function renderTurn(turn: ReplayTurn, open: string): string {
  const blocks = turn.blocks.map((block) => renderBlock(block, open)).join("");
  return `<article data-replay-turn id="${escapeHtml(turn.id)}">
  <div data-slot="aui_user-message-root" class="aui-msg" data-role="user">
    <span class="aui-msg-marker" aria-hidden="true">${dotMatrix("user", { decorative: true })}</span>
    <div class="aui-user-message-content" data-replay-user data-full="${escapeHtml(turn.userText)}">${escapeHtml(turn.userText)}</div>
  </div>
  <div data-slot="aui_assistant-message-root" class="aui-msg" data-role="assistant">
    <div data-slot="aui_assistant-message-content" class="aui-assistant-message-content">
      ${blocks}
    </div>
  </div>
</article>`;
}

function renderBlock(block: ReplayBlock, open: string): string {
  if (block.kind === "text") return renderAnswer(block.markdown);
  if (block.items.length === 0) return "";
  const items = block.items.map((item) => renderChainItem(item, open)).join("");
  return `<div data-replay-block="chain"><details data-replay-chain data-replay-disclosure data-slot="aui_work-chain" class="aui-work-chain"${open}>
  <summary data-slot="aui_work-chain-trigger" class="aui-work-chain-trigger aui-work-status" aria-expanded="${open ? "true" : "false"}">
    <span data-slot="aui_work-status-marker" class="aui-work-status-marker">${dotMatrix("idle", { decorative: true })}</span>
    <span data-slot="aui_work-status-label">Worked</span>
    ${disclosureChevron()}
  </summary>
  <div data-slot="aui_work-chain-content" class="aui-work-chain-content">${items}</div>
</details></div>`;
}

function renderChainItem(item: ReplayChainItem, open: string): string {
  if (item.kind === "reasoning") {
    return `<div data-replay-step="reasoning">
      <details data-replay-disclosure data-slot="reasoning-root" class="aui-reasoning-root"${open}>
        <summary data-slot="reasoning-trigger" class="aui-reasoning-trigger" aria-expanded="${open ? "true" : "false"}">
          <span>Reasoning</span>
          ${disclosureChevron()}
        </summary>
        <div data-slot="reasoning-content" class="aui-reasoning-content">
          <div data-slot="reasoning-text" class="aui-reasoning-text" data-replay-reasoning data-full="${escapeHtml(item.text)}">${escapeHtml(item.text)}</div>
        </div>
      </details>
    </div>`;
  }
  if (item.kind === "notice") {
    const tone = item.notice.tone === "error" ? "error" : "status";
    const detail = item.notice.detail
      ? `<pre class="aui-chat-notice-detail">${escapeHtml(item.notice.detail)}</pre>`
      : "";
    return `<div data-replay-step="notice" class="aui-chat-notice" data-tone="${tone}" data-slot="chat-notice" role="${tone === "error" ? "alert" : "status"}">
      <span class="aui-chat-notice-marker">${dotMatrix(tone === "error" ? "error" : "idle", { decorative: true })}</span>
      <div>
        <div class="aui-chat-notice-title">${escapeHtml(item.notice.title)}</div>
        ${detail}
      </div>
    </div>`;
  }
  return renderTool(item.tool, open);
}

function renderTool(tool: ReplayTool, open: string): string {
  const failed = tool.status === "error" || tool.status === "cancelled";
  const glyph = failed ? "error" : tool.status === "running" ? "idle" : "success";
  const label = failed ? (tool.status === "cancelled" ? "Cancelled tool" : "Failed tool") : "Used tool";
  const args = tool.argsText
    ? `<div data-slot="tool-fallback-args"><div class="aui-tool-fallback-args-header">arguments</div><pre class="aui-tool-fallback-args-value">${escapeHtml(tool.argsText)}</pre></div>`
    : "";
  const error = tool.errorText
    ? `<div class="aui-chat-notice" data-tone="error" data-slot="tool-fallback-error"><div class="aui-tool-fallback-error-header">Error: </div><pre class="aui-tool-fallback-error-reason">${escapeHtml(tool.errorText)}</pre></div>`
    : "";
  const result = tool.resultText
    ? `<div data-replay-result data-slot="tool-fallback-result"><div class="aui-tool-fallback-result-header">result</div><pre class="aui-tool-fallback-result-content">${escapeHtml(tool.resultText)}</pre></div>`
    : "";
  return `<div data-replay-step="tool">
    <details data-replay-disclosure data-slot="tool-fallback-root" class="aui-tool-fallback-root"${open}>
      <summary data-slot="tool-fallback-trigger" class="aui-tool-fallback-trigger" aria-expanded="${open ? "true" : "false"}">
        ${dotMatrix(glyph, { decorative: true })}
        <span data-slot="tool-fallback-trigger-label" class="aui-tool-fallback-trigger-label-wrapper">${label}: <b>${escapeHtml(tool.name)}</b></span>
        ${disclosureChevron()}
      </summary>
      <div data-slot="tool-fallback-content" class="aui-tool-fallback-content">${args}${error}${result}</div>
    </details>
  </div>`;
}

function renderAnswer(markdown: string): string {
  const html = renderMarkdown(markdown);
  return `<div data-replay-block="text" data-replay-answer data-plain="${escapeHtml(markdown)}">
    <div class="aui-md" data-replay-live>${html}</div>
    <template>${html}</template>
  </div>`;
}
