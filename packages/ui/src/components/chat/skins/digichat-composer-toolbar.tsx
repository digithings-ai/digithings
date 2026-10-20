"use client";

import type { EmbedChatPrefsApi } from "../stock/embed-chat-prefs";
import { DigichatContextMeter } from "./digichat-context-meter";

/**
 * Plain-text composer footer for the digichat skin. Shows the selected
 * model and the active backend on the left and the context fill on the
 * right. Clicking the model opens the full settings menu — that is the only
 * control here; the settings button and the per-control chips are gone.
 *
 * The backend chip is a backend indicator, so it appears only where BYOK is
 * on the table (`showByok`) and the host named the backend that serves the
 * chat (`providerLabel`). The label is the host's: this package holds no
 * provider vocabulary, and a host that cannot name the backend shows no
 * chip rather than a wrong one.
 */
export function DigichatComposerToolbar({ prefs }: { prefs: EmbedChatPrefsApi }) {
  const rawModel = prefs.prefs.model.trim();
  // Routing names, not presentation: the backend sees the full model id.
  const modelLabel = rawModel || "auto";
  const providerLabel = prefs.providerLabel?.trim() ?? "";
  const showProvider = prefs.showByok && providerLabel.length > 0;

  // Connected MCP servers and the tools inside them: one ticket server with
  // five tools reads "1 MCP / 5 tools", not "5 MCPs". A server with no
  // sub-tool list counts as one tool. Per-tool toggles live in prefs.extra
  // (tool id -> off).
  const mcpCounts = prefs.mcpServers.reduce(
    (counts, server) => {
      const tools = server.tools ?? [];
      const enabled =
        tools.length === 0
          ? prefs.prefs.extra[server.id] === false
            ? 0
            : 1
          : tools.filter((tool) => prefs.prefs.extra[tool.id] !== false).length;
      if (enabled > 0) {
        counts.servers += 1;
        counts.tools += enabled;
      }
      return counts;
    },
    { servers: 0, tools: 0 },
  );
  const mcpToolTotal = mcpCounts.tools;

  return (
    <div data-slot="aui_composer-toolbar-inner" className="aui-composer-toolbar-inner">
      {prefs.showModels ? (
        <button
          type="button"
          className="aui-composer-meta aui-composer-meta-action"
          onClick={prefs.openModels}
          aria-label="Open models"
        >
          {modelLabel}
        </button>
      ) : (
        <span className="aui-composer-meta">{modelLabel}</span>
      )}
      {showProvider ? (
        <>
          <span className="aui-composer-meta-sep" aria-hidden>
            /
          </span>
          <button
            type="button"
            className="aui-composer-meta aui-composer-meta-action"
            onClick={() => prefs.openByok()}
            aria-label="Open provider menu"
          >
            {providerLabel}
          </button>
        </>
      ) : null}
      {mcpCounts.servers > 0 ? (
        <>
          <span className="aui-composer-meta-sep" aria-hidden>
            /
          </span>
          <button
            type="button"
            className="aui-composer-meta aui-composer-meta-action"
            onClick={() => prefs.openMcp()}
            aria-label="Open MCP servers"
          >
            {mcpCounts.servers} MCP{mcpCounts.servers === 1 ? "" : "s"}
          </button>
          <span className="aui-composer-meta-sep" aria-hidden>
            /
          </span>
          <button
            type="button"
            className="aui-composer-meta aui-composer-meta-action"
            onClick={() => prefs.openTools()}
            aria-label="Open tools"
          >
            {mcpCounts.tools} tool{mcpCounts.tools === 1 ? "" : "s"}
          </button>
        </>
      ) : null}
      <span className="aui-composer-meta-sep" aria-hidden>
        /
      </span>
      <button
        type="button"
        className="aui-composer-meta aui-composer-meta-action"
        onClick={() => prefs.openLanguage()}
        aria-label="Open response language"
      >
        {prefs.prefs.language.slice(0, 2).toUpperCase()}
      </button>
      <span className="aui-composer-meta-spacer" aria-hidden />
      <DigichatContextMeter
        model={rawModel}
        toolCount={mcpToolTotal + prefs.catalogTools.length}
      />
    </div>
  );
}
