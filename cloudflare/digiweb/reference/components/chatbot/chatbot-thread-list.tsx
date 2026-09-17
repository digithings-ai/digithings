"use client";

import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
} from "@assistant-ui/react";

import { DotMatrix } from "@/components/ui/dot-matrix";

/** Terminal-nav conversation list for the gallery chrome specimen. */
export function ChatbotThreadList() {
  return (
    <aside className="aui-chrome-thread-list" aria-label="Conversations">
      <div className="aui-chrome-thread-list-head">
        <span className="aui-chrome-thread-list-label">digichat</span>
        <ThreadListPrimitive.New
          className="aui-chrome-thread-list-new"
          aria-label="New chat"
        >
          <DotMatrix state="newChat" label="New chat" className="size-3.5" />
        </ThreadListPrimitive.New>
      </div>
      <ThreadListPrimitive.Root className="aui-chrome-thread-list-root">
        <ThreadListPrimitive.Items>
          {() => (
            <ThreadListItemPrimitive.Root className="aui-chrome-thread-list-row">
              <ThreadListItemPrimitive.Trigger className="aui-chrome-thread-list-item">
                <ThreadListItemPrimitive.Title fallback="new chat" />
              </ThreadListItemPrimitive.Trigger>
            </ThreadListItemPrimitive.Root>
          )}
        </ThreadListPrimitive.Items>
      </ThreadListPrimitive.Root>
    </aside>
  );
}
