"use client";

import { isToolOrDynamicToolUIPart } from "ai";
import type { UIMessage } from "ai";
import { Wrench } from "lucide-react";

type MsgPart = UIMessage["parts"][number];

export function ToolInvocationCard({ part }: { part: MsgPart }) {
  if (!isToolOrDynamicToolUIPart(part)) {
    return (
      <pre className="overflow-x-auto rounded-md border border-border/50 bg-black/40 p-3 text-xs">
        {JSON.stringify(part, null, 2)}
      </pre>
    );
  }
  if (part.type === "dynamic-tool") {
    return (
      <details className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-xs">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-amber-100/90">
          <Wrench className="h-3.5 w-3.5" />
          <span>{part.toolName}</span>
          <span className="ml-auto rounded bg-background/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {part.state}
          </span>
        </summary>
        <pre className="mt-2 max-h-40 overflow-auto rounded border border-border/40 bg-black/35 p-2 font-mono text-[11px]">
          {JSON.stringify({ input: part.input, output: part.output }, null, 2)}
        </pre>
      </details>
    );
  }
  return (
    <details className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-amber-100/90">
        <Wrench className="h-3.5 w-3.5" />
        <span>{part.type.replace(/^tool-/, "")}</span>
        <span className="ml-auto rounded bg-background/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          {part.state}
        </span>
      </summary>
      <pre className="mt-2 max-h-48 overflow-auto rounded border border-border/40 bg-black/35 p-2 font-mono text-[11px]">
        {JSON.stringify(part, null, 2)}
      </pre>
    </details>
  );
}
