"use client";

import { Fragment, type ReactNode } from "react";
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
  const sessionModel = prefs.prefs.model.trim();
  // The chip names the session model. The bar sizes to the model the turn
  // sends (`meterModel`), including a bring-your-own-key binding.
  const modelLabel = sessionModel || "auto";
  const meterModel = prefs.meterModel?.trim() || sessionModel;
  const providerLabel = prefs.providerLabel?.trim() ?? "";
  // The backend is named whenever the host named one — a Foundry tenant is
  // served by Azure AI Foundry, not by the house model provider. It is a
  // button only where the tenant can switch it.
  const showProvider = providerLabel.length > 0;

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

  // The row is a list of facts separated by slashes. Build the list and
  // join it, so a tenant that has no model (or no provider) never leaves a
  // dangling separator at the front.
  const items: ReactNode[] = [];

  if (prefs.showModels) {
    items.push(
      <button
        key="model"
        type="button"
        className="aui-composer-meta aui-composer-meta-action"
        onClick={prefs.openModels}
        aria-label="Open models"
      >
        {modelLabel}
      </button>,
    );
  }

  if (showProvider) {
    items.push(
      prefs.showByok ? (
        <button
          key="provider"
          type="button"
          className="aui-composer-meta aui-composer-meta-action"
          onClick={() => prefs.openByok()}
          aria-label="Open provider menu"
        >
          {providerLabel}
        </button>
      ) : (
        <span key="provider" className="aui-composer-meta">
          {providerLabel}
        </span>
      ),
    );
  }

  if (mcpCounts.servers > 0) {
    items.push(
      <button
        key="mcp"
        type="button"
        className="aui-composer-meta aui-composer-meta-action"
        onClick={() => prefs.openMcp()}
        aria-label="Open MCP servers"
      >
        {mcpCounts.servers} MCP{mcpCounts.servers === 1 ? "" : "s"}
      </button>,
      <button
        key="tools"
        type="button"
        className="aui-composer-meta aui-composer-meta-action"
        onClick={() => prefs.openTools()}
        aria-label="Open tools"
      >
        {mcpCounts.tools} tool{mcpCounts.tools === 1 ? "" : "s"}
      </button>,
    );
  }

  items.push(
    <button
      key="language"
      type="button"
      className="aui-composer-meta aui-composer-meta-action"
      onClick={() => prefs.openLanguage()}
      aria-label="Open response language"
    >
      {prefs.prefs.language.slice(0, 2).toUpperCase()}
    </button>,
  );

  return (
    <div data-slot="aui_composer-toolbar-inner" className="aui-composer-toolbar-inner">
      {items.map((item, index) => (
        <Fragment key={index}>
          {index > 0 ? (
            <span className="aui-composer-meta-sep" aria-hidden>
              /
            </span>
          ) : null}
          {item}
        </Fragment>
      ))}
      <span className="aui-composer-meta-spacer" aria-hidden />
      {prefs.showContextMeter ? (
        <DigichatContextMeter
          model={meterModel}
          toolCount={mcpToolTotal + prefs.catalogTools.length}
        />
      ) : null}
    </div>
  );
}
