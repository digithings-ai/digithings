"use client";

/**
 * Stock chrome for behaviors that used to live on CliThread slash commands:
 * /lang → language select, /help → help popover, /new → reset conversation.
 * Optional model picker when deploy config enables models.allowPicker.
 */

import { useId, useState, type ReactNode } from "react";
import { LANGUAGES } from "@/lib/languages";
import { cn } from "@/lib/utils";
import {
  Button,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@digithings/ui/ui";

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
        <Label className="flex items-center gap-1.5 text-muted-foreground">
          <span className="sr-only">Reply language</span>
          <Select
            value={language ?? "en"}
            onValueChange={(v) => {
              if (typeof v === "string") onLanguageChange?.(v);
            }}
          >
            <SelectTrigger
              aria-label="Reply language"
              className="h-auto bg-background border-border/60 max-w-[10rem] px-1.5 py-0.5 text-xs"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LANGUAGES.map((l) => (
                <SelectItem key={l.code} value={l.code}>
                  {l.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Label>
      ) : null}

      {showModel ? (
        <Label className="flex items-center gap-1.5 text-muted-foreground">
          <span className="sr-only">Model</span>
          <Select
            value={model ?? models![0]}
            onValueChange={(v) => {
              if (typeof v === "string") onModelChange?.(v);
            }}
          >
            <SelectTrigger
              aria-label="Model"
              className="h-auto bg-background border-border/60 max-w-[12rem] px-1.5 py-0.5 text-xs"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {models!.map((id) => (
                <SelectItem key={id} value={id}>
                  {id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Label>
      ) : null}

      <div className="relative">
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto text-muted-foreground hover:text-foreground rounded px-1.5 py-0.5 underline-offset-2"
          aria-expanded={helpOpen}
          aria-controls={helpId}
          onClick={() => setHelpOpen((o) => !o)}
        >
          Help
        </Button>
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
            <Button
              type="button"
              variant="link"
              size="sm"
              className="mt-2 h-auto text-foreground px-0 underline-offset-2"
              onClick={() => setHelpOpen(false)}
            >
              Close
            </Button>
          </div>
        ) : null}
      </div>

      {showNew ? (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto text-muted-foreground hover:text-foreground rounded px-1.5 py-0.5 underline-offset-2"
          onClick={() => onNewThread?.()}
        >
          New conversation
        </Button>
      ) : null}

      <div className="ml-auto flex items-center gap-2">{trailing}</div>
    </div>
  );
}
