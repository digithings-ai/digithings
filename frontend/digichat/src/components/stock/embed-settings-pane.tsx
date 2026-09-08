"use client";

/**
 * Embed /settings pane (#3733): session tool toggles, language, BYOK.
 * Themed for first-party digichat — not the CLI settings list.
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
  return (
    <div
      className="embed-settings-pane fixed inset-x-0 bottom-0 z-50 border-t border-border bg-background p-4 shadow-lg"
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
        {onByok ? (
          <button type="button" className="dc-inline-link self-start text-xs" onClick={onByok}>
            API key (BYOK)
          </button>
        ) : null}
        <p className="text-muted-foreground text-xs">
          Session only — reload or /new resets to {languageLabel("en")} with tools on.
        </p>
      </div>
    </div>
  );
}
