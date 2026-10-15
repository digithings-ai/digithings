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
import { DigichatWordmark } from "./DigichatWordmark";
import { DotMatrix } from "./DotMatrix";

export type DigichatThreadListProps = {
  className?: string;
  /**
   * Landmark the list renders as. The standalone sidebar is page-level
   * complementary content (`aside`); embedded in a page section (e.g. the
   * digiquant landing chat band) it is a thread navigator inside `<main>`,
   * where a complementary landmark is a violation — pass `"nav"`.
   */
  landmark?: "aside" | "nav";
};

export function DigichatThreadList({ className, landmark = "aside" }: DigichatThreadListProps) {
  const cls = [digichatSurfaces.list, className ?? ""].filter(Boolean).join(" ");
  const Tag = landmark;
  return (
    <Tag className={cls} data-memory-thread-list aria-label="Conversations">
      <div className="flex h-8 shrink-0 items-center justify-between gap-2 border-b border-term-hair px-[0.7rem]">
        <span className="min-w-0 flex-1">
          <DigichatWordmark />
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
    </Tag>
  );
}
