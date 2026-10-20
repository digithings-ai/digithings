"use client";

import type { EmbedChatPrefsApi } from "../stock/embed-chat-prefs";
import { DigichatContextMeter } from "./digichat-context-meter";

/**
 * Plain-text composer footer for the digichat skin. Shows the selected
 * model and the active backend on the left and the context fill on the
 * right. Clicking the model opens the full settings menu — that is the only
 * control here; the settings button and the per-control chips are gone.
 */
export function DigichatComposerToolbar({
  prefs,
  providerLabel = "cheaper inference",
}: {
  prefs: EmbedChatPrefsApi;
  /** Active backend: Cheaper Inference for house models, or a BYOK provider. */
  providerLabel?: string;
}) {
  const rawModel = prefs.prefs.model.trim();
  const modelLabel = rawModel
    ? (rawModel.split("/").pop() ?? rawModel).replace(/-/g, " ")
    : "auto";

  // Connected MCP servers and the tools inside them: one zammad server with
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
      {mcpCounts.servers > 0 ? (
        <>
          <span className="aui-composer-meta-sep" aria-hidden>
            /
          </span>
          <button
            type="button"
            className="aui-composer-meta aui-composer-meta-action"
            onClick={() => prefs.openMcp()}
            aria-label="Open MCP tools"
          >
            {mcpCounts.servers} MCP{mcpCounts.servers === 1 ? "" : "s"} /{" "}
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
