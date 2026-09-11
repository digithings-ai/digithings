"use client";

/**
 * `/mcp` tools pane (#3736). Operator catalog/MCP ids are session toggles
 * (no URLs). Personal browser MCP is only offered when allowUserServers.
 */

import { useEmbedChatPrefs } from "@/components/stock/embed-chat-prefs";

export function EmbedMcpPane({ onClose }: { onClose: () => void }) {
  const api = useEmbedChatPrefs();
  const extraTools = api.catalogTools.filter(
    (t) => t.id !== "digisearch" && t.id !== "digivault" && t.id !== "web_search",
  );
  return (
    <div
      className="embed-settings-pane fixed inset-x-0 bottom-0 z-50 max-h-[min(80vh,32rem)] overflow-y-auto border-t border-border bg-background p-4 shadow-lg"
      data-thread-skin="digichat"
      data-embed-mcp
      role="dialog"
      aria-label="MCP tools"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium">MCP tools</h2>
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground text-xs underline-offset-2 hover:underline"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <div className="flex flex-col gap-3 text-sm">
        <p className="text-muted-foreground text-xs">
          Enable or disable tools for this session. Reload or /new resets them on.
        </p>
        {api.hasDigisearch ? (
          <label className="flex items-center justify-between gap-3">
            <span>Corpus search</span>
            <input
              type="checkbox"
              checked={api.prefs.digisearch}
              onChange={() => api.setDigisearch(!api.prefs.digisearch)}
            />
          </label>
        ) : null}
        {api.hasVault ? (
          <label className="flex items-center justify-between gap-3">
            <span>Vault</span>
            <input
              type="checkbox"
              checked={api.prefs.vault}
              onChange={() => api.setVault(!api.prefs.vault)}
            />
          </label>
        ) : null}
        {api.tenantAllowsWeb ? (
          <label className="flex items-center justify-between gap-3">
            <span>Web search</span>
            <input
              type="checkbox"
              checked={api.prefs.webSearch}
              onChange={() => api.setWebSearch(!api.prefs.webSearch)}
            />
          </label>
        ) : null}
        {extraTools.map((t) => (
          <label key={t.id} className="flex items-center justify-between gap-3">
            <span>{t.label?.trim() || t.id}</span>
            <input
              type="checkbox"
              checked={api.extraToolOn(t.id)}
              onChange={() => api.setExtraTool(t.id, !api.extraToolOn(t.id))}
            />
          </label>
        ))}
        {api.allowUserMcp ? (
          <p className="text-muted-foreground text-xs">
            {api.allowAddMcp
              ? "This install allows personal Streamable HTTP MCP servers in the browser. They never send URLs through the BFF."
              : "Personal MCP connectors are enabled for this install. The add-server form is hidden."}
          </p>
        ) : (
          <p className="text-muted-foreground text-xs">
            Extra MCP tools come from this deployment. Visitors cannot add servers.
          </p>
        )}
      </div>
    </div>
  );
}
