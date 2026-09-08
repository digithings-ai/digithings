"use client";

import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
} from "@assistant-ui/react";

/** Terminal-nav conversation list for the gallery chrome specimen. */
export function ChatbotThreadList() {
  return (
    <aside className="aui-chrome-thread-list" aria-label="Conversations">
      <div className="aui-chrome-thread-list-head">
        <span className="aui-chrome-thread-list-label">chats</span>
        <ThreadListPrimitive.New className="aui-chrome-thread-list-new">
          + new
        </ThreadListPrimitive.New>
      </div>
      <ThreadListPrimitive.Root className="aui-chrome-thread-list-root">
        <ThreadListPrimitive.Items>
          {() => (
            <ThreadListItemPrimitive.Root className="aui-chrome-thread-list-row">
              <ThreadListItemPrimitive.Trigger className="aui-chrome-thread-list-item">
                <span className="aui-chrome-thread-list-mark" aria-hidden="true">
                  ·{" "}
                </span>
                <ThreadListItemPrimitive.Title fallback="new chat" />
              </ThreadListItemPrimitive.Trigger>
            </ThreadListItemPrimitive.Root>
          )}
        </ThreadListPrimitive.Items>
      </ThreadListPrimitive.Root>
    </aside>
  );
}
