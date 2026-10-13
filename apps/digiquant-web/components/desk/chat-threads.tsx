"use client";

import { Button } from "@digithings/ui/ui";
import type { DeskThread } from "./chat-model";

/** Real chat threads, in the same row style as the desk rail. No placeholder tags.
 *  Only the open thread carries the ▸ marker and the `.on` wash. */
export function ChatThreadRows({
  threads,
  activeId,
  onSelect,
}: {
  threads: DeskThread[];
  activeId?: string;
  onSelect: (id: string) => void;
}) {
  if (!threads.length) return null;
  return (
    <div className="nav-group">
      <div className="nav-title">threads</div>
      {threads.map((thread) => {
        const on = thread.id === activeId;
        return (
          <div className="nav-row" key={thread.id} data-active={on ? "true" : undefined}>
            <span className={on ? "nav-tri text-accent" : "nav-tri"} aria-hidden="true">
              {on ? "▸" : ""}
            </span>
            <Button
              type="button"
              variant="ghost"
              className={`nav-link h-7 min-h-7 flex-1 justify-start rounded-none border-0 px-0 font-mono text-[0.75rem] font-normal shadow-none${on ? " on" : " bg-transparent"}`}
              aria-current={on ? "true" : undefined}
              onClick={() => onSelect(thread.id)}
            >
              <span className="nav-path">{thread.title}</span>
            </Button>
          </div>
        );
      })}
    </div>
  );
}
