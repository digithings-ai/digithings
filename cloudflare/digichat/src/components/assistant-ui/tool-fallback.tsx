"use client";

/**
 * assistant-ui default tool-call fallback (their documented ToolFallback UX).
 * Product-specific tool UIs can replace this later via tools.by_name.
 */
import { useState, type FC } from "react";
import type { ToolCallMessagePartProps } from "@assistant-ui/react";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toolRowTitle } from "@/lib/adapters/digithings/activity/tool-display";

export const ToolFallback: FC<ToolCallMessagePartProps> = ({
  toolName,
  args,
  argsText,
  result,
  status,
  isError,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(true);
  const running = status?.type === "running";
  const title = toolRowTitle(toolName, args);
  const resultText =
    result === undefined
      ? null
      : typeof result === "string"
        ? result
        : JSON.stringify(result, null, 2);

  return (
    <div className="mb-3 flex w-full flex-col gap-2 rounded-none border border-border/40 py-2">
      <div className="flex items-center gap-2 px-3">
        <CheckIcon className="size-3.5 shrink-0 opacity-70" aria-hidden />
        <p className="text-xs">
          {running ? "Running tool: " : isError ? "Tool failed: " : "Used tool: "}
          <b>{title}</b>
        </p>
        <div className="flex-grow" />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 px-1"
          onClick={() => setIsCollapsed((open) => !open)}
          aria-expanded={!isCollapsed}
        >
          {isCollapsed ? (
            <ChevronUpIcon className="size-3.5" />
          ) : (
            <ChevronDownIcon className="size-3.5" />
          )}
        </Button>
      </div>
      {!isCollapsed ? (
        <div className="flex flex-col gap-2 border-t border-border/40 pt-2">
          {argsText ? (
            <pre className="overflow-auto px-3 font-mono text-[11px] whitespace-pre-wrap text-muted-foreground">
              {argsText}
            </pre>
          ) : null}
          {resultText ? (
            <div className="border-t border-dashed border-border/40 px-3 pt-2">
              <p className="text-[11px] font-semibold">Result</p>
              <pre className="overflow-auto font-mono text-[11px] whitespace-pre-wrap text-muted-foreground">
                {resultText}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
