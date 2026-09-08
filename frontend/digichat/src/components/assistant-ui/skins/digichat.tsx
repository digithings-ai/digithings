"use client";

import "@digithings/web/styles/chat-core.css";
import "@digithings/web/styles/chat-widgets.css";
import "@digithings/web/styles/chat-aui.css";
import "@digithings/web/styles/chatbot.css";

import { useCallback, useMemo, type FormEvent } from "react";
import {
  unstable_useSlashCommandAdapter,
  useAui,
  type Unstable_TriggerItem,
} from "@assistant-ui/react";
import {
  Copy,
  Download,
  Folder,
  Globe,
  HelpCircle,
  Key,
  Languages,
  Plus,
  Search,
  Settings,
  Slash,
} from "lucide-react";
import {
  copyMarkdownWithFallback,
  downloadMarkdown,
  serializeAssistantMarkdown,
  serializeThreadMarkdown,
  type TranscriptTurn,
} from "@digithings/digichat-ui";
import { DigichatThread } from "@digithings/web/chat/thread";
import { useComposerCopy, useSkinChrome } from "@/components/stock/skin-chrome";
import { useStockComposerGateSubmit, useStockSendGate } from "@/components/stock/stock-send-gate";
import { useEmbedChatPrefsOptional } from "@/components/stock/embed-chat-prefs";
import {
  buildProductSlashCommands,
  executeSlashDef,
  slashItemPrefixMatch,
  slashSubmitAction,
} from "@/lib/product-slash-commands";
import { armForceToolThenHold, setPendingForceTool } from "@/lib/pending-chat-headers";

const SLASH_ICON_MAP = {
  Globe,
  Search,
  Folder,
  Languages,
  Settings,
  Key,
  HelpCircle,
  Plus,
  Copy,
  Download,
  Slash,
};

/**
 * First-party digichat Thread. Explicit ThreadSkinView branch — never fall
 * through to product-page-assistant. Always left-aligned regardless of YAML.
 */
export function DigichatSkin() {
  const { welcome, welcomeBody, placeholder } = useComposerCopy(
    "What should we inspect?",
    "Ask digichat…",
  );
  const { mode } = useSkinChrome();
  const gateSubmit = useStockComposerGateSubmit();
  const gate = useStockSendGate();
  const prefs = useEmbedChatPrefsOptional();
  const aui = useAui();
  const slashPrefs = useMemo(() => {
    if (!prefs) return null;
    return {
      ...prefs,
      newThread: () => {
        prefs.newThread();
        aui.threads.switchToNewThread();
      },
    };
  }, [prefs, aui]);
  const enableSlash = Boolean(slashPrefs) && mode !== "app";

  const copyExport = useMemo(
    () => ({
      copy: () => {
        const turns = threadTurns(aui.thread().getState().messages);
        const last = [...turns].reverse().find((t) => t.role === "assistant");
        if (!last) return;
        void copyMarkdownWithFallback(serializeAssistantMarkdown(last.content, last.sources));
      },
      exportThread: () => {
        const md = serializeThreadMarkdown(threadTurns(aui.thread().getState().messages));
        if (md) downloadMarkdown("digichat.md", md);
      },
    }),
    [aui],
  );

  const commands = useMemo(() => {
    if (!enableSlash || !slashPrefs) return [];
    return buildProductSlashCommands(slashPrefs).map((c) => {
      if (c.id === "copy") return { ...c, execute: copyExport.copy };
      if (c.id === "export") return { ...c, execute: copyExport.exportThread };
      if (c.id === "search") {
        return {
          ...c,
          execute: () => {
            queueMicrotask(() => aui.composer.setText("/search "));
          },
        };
      }
      if (c.id === "vault") {
        return {
          ...c,
          execute: () => {
            queueMicrotask(() => aui.composer.setText("/vault "));
          },
        };
      }
      return c;
    });
  }, [enableSlash, slashPrefs, copyExport, aui]);

  const slash = unstable_useSlashCommandAdapter({
    commands,
    removeOnExecute: true,
    iconMap: SLASH_ICON_MAP,
    fallbackIcon: Slash,
  });
  const slashTrigger = useMemo(() => {
    const inner = slash.adapter;
    return {
      ...slash,
      adapter: {
        ...inner,
        search: (query: string) => {
          const searchFn = inner.search;
          if (typeof searchFn !== "function") return [];
          const raw: unknown = searchFn(query);
          const keep = (items: readonly Unstable_TriggerItem[]) =>
            items.filter((item) => slashItemPrefixMatch(item, query));
          if (
            raw !== null &&
            typeof raw === "object" &&
            "then" in raw &&
            typeof (raw as PromiseLike<readonly Unstable_TriggerItem[]>).then === "function"
          ) {
            return Promise.resolve(raw as PromiseLike<readonly Unstable_TriggerItem[]>).then(
              keep,
            );
          }
          return keep(Array.isArray(raw) ? raw : []);
        },
      },
    };
  }, [slash]);

  const onComposerSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      if (slashPrefs) {
        const text = aui.composer.getState().text;
        const action = slashSubmitAction(text);
        if (action.kind === "block") {
          event.preventDefault();
          return;
        }
        if (action.kind === "force") {
          event.preventDefault();
          if (gate?.shouldHold(action.text)) {
            aui.composer.setText("");
            void aui.composer.clearAttachments();
            armForceToolThenHold(slashPrefs.sessionKey, action.forceTool, () => {
              gate.onHold(action.text);
            });
            return;
          }
          setPendingForceTool(slashPrefs.sessionKey, action.forceTool);
          aui.composer.setText(action.text);
          gate?.onAllowSend?.();
          aui.composer.send();
          return;
        }
        if (action.kind === "run") {
          event.preventDefault();
          if (action.command.id === "copy") copyExport.copy();
          else if (action.command.id === "export") copyExport.exportThread();
          else executeSlashDef(action.command, action.arg, slashPrefs);
          aui.composer.setText("");
          return;
        }
      }
      gateSubmit?.(event);
    },
    [slashPrefs, aui, gate, gateSubmit, copyExport],
  );

  return (
    <DigichatThread
      welcome={welcome}
      welcomeBody={welcomeBody}
      placeholder={placeholder}
      onComposerSubmit={onComposerSubmit}
      composerLayout={mode === "app" ? "expanded" : "compact"}
      slash={enableSlash ? slashTrigger : undefined}
    />
  );
}

function threadTurns(messages: readonly unknown[]): TranscriptTurn[] {
  const out: TranscriptTurn[] = [];
  for (const raw of messages) {
    if (!raw || typeof raw !== "object") continue;
    const m = raw as { role?: string; content?: unknown; parts?: unknown };
    if (m.role !== "user" && m.role !== "assistant") continue;
    const parts = Array.isArray(m.content) ? m.content : m.parts;
    const text = Array.isArray(parts)
      ? parts
          .filter((p): p is { type: string; text?: string } => !!p && typeof p === "object")
          .filter((p) => p.type === "text" && typeof p.text === "string")
          .map((p) => p.text ?? "")
          .join("")
      : "";
    if (!text.trim()) continue;
    out.push({ role: m.role, content: text });
  }
  return out;
}
