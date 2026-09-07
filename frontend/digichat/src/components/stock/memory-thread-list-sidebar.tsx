"use client";

/**
 * Sidebar for persistence=memory — ThreadListPrimitive against the active
 * AssistantRuntime (from useRemoteThreadListRuntime).
 */

import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
} from "@assistant-ui/react";

export function MemoryThreadListSidebar() {
  return (
    <aside
      className="border-border/50 bg-muted/20 flex w-56 shrink-0 flex-col border-r"
      data-memory-thread-list
      aria-label="Conversations"
    >
      <div className="flex items-center justify-between gap-2 border-b border-border/40 px-2 py-2">
        <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Chats
        </span>
        <ThreadListPrimitive.New className="text-foreground hover:bg-muted rounded px-2 py-1 text-xs">
          New
        </ThreadListPrimitive.New>
      </div>
      <ThreadListPrimitive.Root className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-1">
        <ThreadListPrimitive.Items>
          {() => (
            <ThreadListItemPrimitive.Root className="data-[active]:bg-muted hover:bg-muted/60 rounded px-2 py-1.5 text-sm">
              <ThreadListItemPrimitive.Trigger className="w-full truncate text-left">
                <ThreadListItemPrimitive.Title fallback="New chat" />
              </ThreadListItemPrimitive.Trigger>
            </ThreadListItemPrimitive.Root>
          )}
        </ThreadListPrimitive.Items>
      </ThreadListPrimitive.Root>
    </aside>
  );
}
