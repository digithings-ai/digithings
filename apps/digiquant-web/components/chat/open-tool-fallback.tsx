"use client";

import { useState } from "react";
import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import {
  ToolFallbackArgs,
  ToolFallbackContent,
  ToolFallbackResult,
  ToolFallbackRoot,
  ToolFallbackTrigger,
} from "../../../../packages/ui/src/components/chat/gallery-thread/tool-fallback.aui";

/**
 * The digichat tool row, held open so an example result is on screen.
 * Same Root / Trigger / Args / Result parts the thread uses; only the
 * disclosure starts open, because this page has no one to click.
 */
export const OpenToolFallback: ToolCallMessagePartComponent = ({
  toolName,
  argsText,
  result,
  status,
  isError,
}) => {
  const [open, setOpen] = useState(true);
  const effective =
    isError && status?.type !== "incomplete"
      ? { type: "incomplete" as const, reason: "error" as const }
      : status;
  return (
    <ToolFallbackRoot open={open} onOpenChange={setOpen}>
      <ToolFallbackTrigger toolName={toolName} argsText={argsText} status={effective} />
      <ToolFallbackContent>
        <ToolFallbackArgs argsText={argsText} />
        {result !== undefined && !isError ? <ToolFallbackResult result={result} /> : null}
      </ToolFallbackContent>
    </ToolFallbackRoot>
  );
};
