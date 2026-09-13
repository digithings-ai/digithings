"use client";

/**
 * Stock chrome for behaviors that used to live on CliThread slash commands:
 * /lang → language select, /help → help popover, /new → reset conversation.
 * Optional model picker when deploy config enables models.allowPicker.
 */

import { useId, useState, type ReactNode } from "react";
import { LANGUAGES } from "@/lib/languages";
import { cn } from "@/lib/utils";

export type StockChromeBarProps = {
  language?: string;
  onLanguageChange?: (code: string) => void;
  onNewThread?: () => void;
  /** Model ids from deploy `models.available` (picker only when onModelChange set). */
  models?: readonly string[];
  model?: string;
  onModelChange?: (modelId: string) => void;
  /** Extra help lines (tenant tools, etc.). */
  helpExtra?: readonly string[];
  className?: string;
  trailing?: ReactNode;
};

const DEFAULT_HELP = [
  "Ask a question in the composer below.",
  "Use the tool toggles (when shown) to force search / vault / web search.",
  "Language controls the assistant reply language for this session.",
  "New conversation clears the current thread (embed) or starts another (app).",
];

export function StockChromeBar({
  language,
  onLanguageChange,
  onNewThread,
  models,
  model,
  onModelChange,
  helpExtra,
  className,
  trailing,
}: StockChromeBarProps) {
  const helpId = useId();
  const [helpOpen, setHelpOpen] = useState(false);
  const showLang = typeof onLanguageChange === "function";
  const showNew = typeof onNewThread === "function";
  const showModel =
    typeof onModelChange === "function" && (models?.length ?? 0) > 0;
  if (!showLang && !showNew && !showModel && !trailing) return null;

  const helpLines = [
    ...DEFAULT_HELP,
    ...(showModel ? ["Model selects which allowlisted model the BFF may use."] : []),
    ...(helpExtra ?? []),
  ];

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 border-b border-border/40 px-3 py-1.5 text-xs",
        className,
      )}
      data-stock-chrome
    >
      {showLang ? (
        <label className="flex items-center gap-1.5 text-muted-foreground">
          <span className="sr-only">Reply language</span>
          <select
            className="bg-background border-border/60 max-w-[10rem] rounded border px-1.5 py-0.5"
            value={language ?? "en"}
            onChange={(e) => onLanguageChange?.(e.target.value)}
            aria-label="Reply language"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {showModel ? (
        <label className="flex items-center gap-1.5 text-muted-foreground">
          <span className="sr-only">Model</span>
          <select
            className="bg-background border-border/60 max-w-[12rem] rounded border px-1.5 py-0.5"
            value={model ?? models![0]}
            onChange={(e) => onModelChange?.(e.target.value)}
            aria-label="Model"
          >
            {models!.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <div className="relative">
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground rounded px-1.5 py-0.5 underline-offset-2 hover:underline"
          aria-expanded={helpOpen}
          aria-controls={helpId}
          onClick={() => setHelpOpen((o) => !o)}
        >
          Help
        </button>
        {helpOpen ? (
          <div
            id={helpId}
            role="dialog"
            aria-label="Help"
            className="bg-background border-border absolute left-0 z-20 mt-1 w-72 rounded border p-3 text-left shadow-md"
          >
            <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
              {helpLines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <button
              type="button"
              className="text-foreground mt-2 underline"
              onClick={() => setHelpOpen(false)}
            >
              Close
            </button>
          </div>
        ) : null}
      </div>

      {showNew ? (
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground rounded px-1.5 py-0.5 underline-offset-2 hover:underline"
          onClick={() => onNewThread?.()}
        >
          New conversation
        </button>
      ) : null}

      <div className="ml-auto flex items-center gap-2">{trailing}</div>
    </div>
  );
}
