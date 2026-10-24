"use client";

/**
 * Sidebar for persistence=memory — ThreadListPrimitive against the active
 * AssistantRuntime (from useRemoteThreadListRuntime). First-party `digichat`
 * uses the terminal list; catalog skins keep the muted rail.
 */

import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
} from "@assistant-ui/react";
import { DigichatThreadList } from "@digithings/ui/chat/thread-list";
import { useSkinChrome } from "@digithings/ui/chat/stock";

export function MemoryThreadListSidebar() {
  const { skin } = useSkinChrome();
  if (skin === "digichat") {
    return <DigichatThreadList />;
  }
  return (
    <aside
      className="app-thread-rail"
      data-memory-thread-list
      aria-label="Conversations"
    >
      <div className="app-thread-rail-head">
        <span className="app-thread-rail-label">chats</span>
        <ThreadListPrimitive.New className="app-thread-rail-new">
          + new
        </ThreadListPrimitive.New>
      </div>
      <ThreadListPrimitive.Root className="dc-thread-list app-thread-rail-list">
        <ThreadListPrimitive.Items>
          {() => (
            <ThreadListItemPrimitive.Root className="app-thread-rail-item data-[active]:bg-surface-2 hover:bg-surface-2">
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
