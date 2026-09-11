"use client";

/**
 * Embed /settings pane (#3733 / #3736): session tool toggles (including extra
 * MCP catalog ids), language, model/effort, thinking, BYOK.
 */

import { useEmbedChatPrefs } from "@/components/stock/embed-chat-prefs";
import { languageSelectOptions } from "@/lib/product-slash-commands";
import { languageLabel } from "@/lib/languages";

export function EmbedSettingsPane({
  onClose,
  onByok,
}: {
  onClose: () => void;
  onByok?: () => void;
}) {
  const api = useEmbedChatPrefs();
  const options = languageSelectOptions();
  const extraTools = api.catalogTools.filter(
    (t) => t.id !== "digisearch" && t.id !== "digivault" && t.id !== "web_search",
  );
  return (
    <div
      className="embed-settings-pane fixed inset-x-0 bottom-0 z-50 max-h-[min(80vh,32rem)] overflow-y-auto border-t border-border bg-background p-4 shadow-lg"
      data-thread-skin="digichat"
      data-embed-settings
      role="dialog"
      aria-label="Settings"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium">Settings</h2>
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground text-xs underline-offset-2 hover:underline"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <div className="flex flex-col gap-3 text-sm">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Tools
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
        <label className="flex items-center justify-between gap-3">
          <span>Reasoning</span>
          <input
            type="checkbox"
            checked={api.prefs.thinking}
            onChange={() => api.setThinking(!api.prefs.thinking)}
          />
        </label>
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Session
        </p>
        <label className="flex items-center justify-between gap-3">
          <span>Language</span>
          <select
            className="bg-background border-border/60 max-w-[12rem] rounded border px-1.5 py-0.5"
            value={api.prefs.language}
            onChange={(e) => api.setLanguage(e.target.value)}
            aria-label="Reply language"
          >
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {api.showModels ? (
          <>
            <label className="flex items-center justify-between gap-3">
              <span>Model</span>
              <button
                type="button"
                className="dc-inline-link text-xs"
                onClick={() => {
                  api.openModels();
                  onClose();
                }}
              >
                {api.prefs.model || "Pick model"}
              </button>
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>Effort</span>
              <select
                className="bg-background border-border/60 max-w-[12rem] rounded border px-1.5 py-0.5"
                value={api.prefs.effort}
                onChange={(e) => api.setEffort(e.target.value)}
                aria-label="Reasoning effort"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>
          </>
        ) : null}
        {onByok ? (
          <button type="button" className="dc-inline-link self-start text-xs" onClick={onByok}>
            API key (BYOK)
          </button>
        ) : null}
        {api.allowUserMcp ? (
          <p className="text-muted-foreground text-xs">
            This install allows personal MCP servers — use /mcp to connect.
          </p>
        ) : (
          <p className="text-muted-foreground text-xs">
            MCP tools come from this deployment. Session only — reload or /new resets to{" "}
            {languageLabel("en")} with tools on.
          </p>
        )}
      </div>
    </div>
  );
}
