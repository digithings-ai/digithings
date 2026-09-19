"use client";

/**
 * DigichatThreadList — terminal-nav conversation list (not a ChatGPT history
 * rail). Wraps ThreadListPrimitive so gallery mocks and product memory
 * persistence share one dress.
 */
import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
} from "@assistant-ui/react";

import { digichatSurfaces } from "./chat-surfaces";
import { DotMatrix } from "./DotMatrix";

export type DigichatThreadListProps = {
  className?: string;
};

export function DigichatThreadList({ className }: DigichatThreadListProps) {
  const cls = [digichatSurfaces.list, className ?? ""].filter(Boolean).join(" ");
  return (
    <aside className={cls} data-memory-thread-list aria-label="Conversations">
      <div className="flex items-center justify-between gap-2 border-b border-term-hair px-[0.7rem] py-[0.55rem]">
        <span className="font-mono text-[0.62rem] tracking-[0.06em] text-term-mute">
          {"digichat"}
        </span>
        <ThreadListPrimitive.New className={digichatSurfaces.action} aria-label="New chat">
          <DotMatrix state="newChat" label="New chat" className="size-3.5" />
        </ThreadListPrimitive.New>
      </div>
      <ThreadListPrimitive.Root className="flex min-h-0 flex-1 flex-col overflow-y-auto py-[0.25rem]">
        <ThreadListPrimitive.Items>
          {() => (
            <ThreadListItemPrimitive.Root className="rounded-none">
              <ThreadListItemPrimitive.Trigger className={digichatSurfaces.listItem}>
                <ThreadListItemPrimitive.Title fallback="new chat" />
              </ThreadListItemPrimitive.Trigger>
            </ThreadListItemPrimitive.Root>
          )}
        </ThreadListPrimitive.Items>
      </ThreadListPrimitive.Root>
    </aside>
  );
}
