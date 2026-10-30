"use client";

import { ActionBarMorePrimitive, useAui, useAuiState } from "@assistant-ui/react";
import { ChevronRightIcon } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import { useCallback, useMemo, useRef, useState, type ReactElement, type ReactNode } from "react";

import { exportMessage } from "../../../replay/chat-export-run";
import { messageAnchor } from "../../../replay/snapshot";
import {
  CHAT_EXPORT_FORMATS,
  chatExportLabel,
  chatExportStrings,
  type ChatExportFormat,
  type ChatExportStrings,
} from "../transcript";
import { useEmbedChatPrefsOptional } from "./embed-chat-prefs";

/** Export strings in the session language (`/language`), else English. */
export function useChatExportStrings(): ChatExportStrings {
  const prefs = useEmbedChatPrefsOptional();
  const locale = prefs?.prefs.language;
  return useMemo(() => chatExportStrings(locale), [locale]);
}

export type MessageExportMenuProps = {
  /** The "…" button. It must forward its ref (TooltipIconButton does). */
  trigger: ReactElement;
  /** Drawn before "Export" in the menu. */
  icon?: ReactNode;
  /** Drawn before each format row. */
  formatIcon?: (format: ChatExportFormat) => ReactNode;
  contentClassName: string;
  /** The side panel. Defaults to `contentClassName`. */
  subContentClassName?: string;
  itemClassName: string;
  side?: "top" | "bottom" | "left" | "right";
  align?: "start" | "center" | "end";
  sideOffset?: number;
};

/**
 * The message "…" menu: `Export ▸` with `Markdown (.md)` and `HTML (.html)`
 * in a side panel. Both export this assistant message only.
 *
 * assistant-ui's more-menu has no submenu, so the menu is radix's own
 * DropdownMenu. `ActionBarMorePrimitive.Root` still wraps it, controlled by
 * the same open state, so the action bar stays visible while the menu is
 * open. The export runs after the menu has closed: the HTML snapshot reads
 * the page, and an open menu hides the thread from it.
 */
export function MessageExportMenu({
  trigger,
  icon,
  formatIcon,
  contentClassName,
  subContentClassName,
  itemClassName,
  side = "bottom",
  align = "start",
  sideOffset = 6,
}: MessageExportMenuProps) {
  const aui = useAui();
  const messageId = useAuiState((s) => s.message.id);
  const strings = useChatExportStrings();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const pending = useRef<ChatExportFormat | null>(null);

  const run = useCallback(
    (format: ChatExportFormat) => {
      // Resolve the message element now: an older answer's action bar can
      // unmount once the menu closes, taking the trigger with it.
      const trigger = messageAnchor(triggerRef.current, messageId) ?? triggerRef.current;
      const message = aui.message().getState();
      const messages = aui.thread().getState().messages;
      requestAnimationFrame(() => {
        void exportMessage({ format, message, messageId, messages, trigger });
      });
    },
    [aui, messageId],
  );

  const onOpenChange = useCallback(
    (next: boolean) => {
      setOpen(next);
      if (next) return;
      const format = pending.current;
      pending.current = null;
      if (format) run(format);
    },
    [run],
  );

  return (
    <ActionBarMorePrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DropdownMenu.Root open={open} onOpenChange={onOpenChange}>
        <DropdownMenu.Trigger asChild ref={triggerRef}>
          {trigger}
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            side={side}
            align={align}
            sideOffset={sideOffset}
            data-slot="message-more-menu"
            className={contentClassName}
          >
            <DropdownMenu.Sub>
              <DropdownMenu.SubTrigger
                data-slot="message-export-trigger"
                className={itemClassName}
              >
                {icon}
                <span className="flex-1">{strings.export}</span>
                <ChevronRightIcon aria-hidden className="size-3.5 opacity-70 rtl:rotate-180" />
              </DropdownMenu.SubTrigger>
              <DropdownMenu.Portal>
                <DropdownMenu.SubContent
                  sideOffset={4}
                  alignOffset={-4}
                  data-slot="message-export-formats"
                  className={subContentClassName ?? contentClassName}
                >
                  {CHAT_EXPORT_FORMATS.map((format) => (
                    <DropdownMenu.Item
                      key={format}
                      data-export-format={format}
                      className={itemClassName}
                      onSelect={() => {
                        pending.current = format;
                      }}
                    >
                      {formatIcon?.(format)}
                      {chatExportLabel(format, strings)}
                    </DropdownMenu.Item>
                  ))}
                </DropdownMenu.SubContent>
              </DropdownMenu.Portal>
            </DropdownMenu.Sub>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </ActionBarMorePrimitive.Root>
  );
}
