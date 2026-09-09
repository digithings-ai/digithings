"use client";

/**
 * In-chat tool toggles driven by deployment tools.catalog.
 * Server allowlist remains source of truth for X-Digi-Force-Tool / web search.
 */

import { useCallback, useMemo, useState } from "react";
import type { DigichatClientConfig } from "@/lib/deploy-config";
import { FORCE_TOOL_BY_CATALOG_ID } from "@/lib/deploy-config";
import { setPendingForceTool } from "@/lib/pending-chat-headers";
import {
  isWebSearchEnabled,
  readWebSearchPref,
  writeWebSearchPref,
} from "@/lib/web-search-pref";
import { cn } from "@/lib/utils";

export type ToolCatalogBarProps = {
  clientConfig: DigichatClientConfig;
  /** Session key for pending force-tool (embed host or thread id). */
  sessionKey: string;
  /** localStorage scope for web search; defaults to sessionKey. */
  webSearchScope?: string;
  className?: string;
  onWebSearchChange?: (enabled: boolean) => void;
};

export function ToolCatalogBar({
  clientConfig,
  sessionKey,
  webSearchScope,
  className,
  onWebSearchChange,
}: ToolCatalogBarProps) {
  const { tools, gate } = clientConfig;
  const catalog = tools.catalog;
  const allowToggle = tools.allowUserToggle;
  const prefScope = webSearchScope?.trim() || sessionKey;

  const tenantAllowsWeb =
    gate.webSearch === true || catalog.some((t) => t.id === "web_search");

  const [webPref, setWebPref] = useState(() =>
    typeof window !== "undefined" ? readWebSearchPref(prefScope) : false,
  );
  const [armedForce, setArmedForce] = useState<string | null>(null);

  const webOn = isWebSearchEnabled({
    tenantAllows: tenantAllowsWeb,
    userPref: webPref,
  });

  const toggleWeb = useCallback(() => {
    if (!allowToggle || !tenantAllowsWeb) return;
    const next = !webPref;
    writeWebSearchPref(prefScope, next);
    setWebPref(next);
    onWebSearchChange?.(next);
  }, [allowToggle, tenantAllowsWeb, webPref, prefScope, onWebSearchChange, setWebPref]);

  const toggleForce = useCallback(
    (catalogId: string) => {
      if (!allowToggle) return;
      const force = FORCE_TOOL_BY_CATALOG_ID[catalogId];
      if (!force) return;
      const next = armedForce === force ? null : force;
      setArmedForce(next);
      setPendingForceTool(sessionKey, next ?? undefined);
    },
    [allowToggle, armedForce, sessionKey, setArmedForce],
  );

  const entries = useMemo(
    () =>
      catalog.filter(
        (e) => e.id === "web_search" || FORCE_TOOL_BY_CATALOG_ID[e.id],
      ),
    [catalog],
  );

  if (!entries.length || !allowToggle) return null;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 border-b border-border/40 px-3 py-2 text-xs",
        className,
      )}
      data-tool-catalog
      role="group"
      aria-label="Tools"
    >
      {entries.map((entry) => {
        if (entry.id === "web_search") {
          return (
            <button
              key={entry.id}
              type="button"
              className={cn(
                "rounded-md border px-2 py-1 transition-colors",
                webOn
                  ? "border-foreground/40 bg-muted"
                  : "border-border text-muted-foreground",
              )}
              aria-pressed={webOn}
              onClick={toggleWeb}
            >
              {entry.label ?? "Web search"}
            </button>
          );
        }
        const force = FORCE_TOOL_BY_CATALOG_ID[entry.id]!;
        const on = armedForce === force;
        return (
          <button
            key={entry.id}
            type="button"
            className={cn(
              "rounded-md border px-2 py-1 transition-colors",
              on
                ? "border-foreground/40 bg-muted"
                : "border-border text-muted-foreground",
            )}
            aria-pressed={on}
            onClick={() => toggleForce(entry.id)}
            title={`Arm ${force} for next send`}
          >
            {entry.label ?? entry.id}
          </button>
        );
      })}
    </div>
  );
}
