"use client";

/**
 * `/models` pane (#3736): searchable allowlisted models + effort.
 * House installs list cheap/free LiteLLM aliases only — never the full OmniRoute dump.
 */

import { useMemo, useState } from "react";
import { useEmbedChatPrefs } from "@/components/stock/embed-chat-prefs";

export function EmbedModelsPane({
  models,
  onClose,
}: {
  models: readonly string[];
  onClose: () => void;
}) {
  const api = useEmbedChatPrefs();
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return models;
    return models.filter((id) => id.toLowerCase().includes(needle));
  }, [models, q]);

  return (
    <div
      className="embed-settings-pane fixed inset-x-0 bottom-0 z-50 max-h-[min(80vh,32rem)] overflow-y-auto border-t border-border bg-background p-4 shadow-lg"
      data-thread-skin="digichat"
      data-embed-models
      role="dialog"
      aria-label="Models"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium">Models</h2>
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground text-xs underline-offset-2 hover:underline"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <div className="flex flex-col gap-3 text-sm">
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
        {models.length ? (
          <>
            <input
              className="bg-background border-border/60 rounded border px-2 py-1 text-sm"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search models"
              aria-label="Search models"
            />
            <ul className="flex max-h-56 flex-col gap-1 overflow-y-auto">
              {filtered.map((id) => (
                <li key={id}>
                  <button
                    type="button"
                    className={`w-full rounded px-2 py-1 text-left text-sm ${
                      api.prefs.model === id ? "bg-accent" : "hover:bg-accent/50"
                    }`}
                    onClick={() => api.setModel(id)}
                  >
                    {id}
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-muted-foreground text-xs">
            This deployment does not publish a model list.
          </p>
        )}
      </div>
    </div>
  );
}
