"use client";

import "@digithings/web/styles/chat-core.css";
import "@digithings/web/styles/chat-widgets.css";
import "@digithings/web/styles/chat-aui.css";
import "@digithings/web/styles/chatbot.css";

import { useCallback, useMemo, type FormEvent } from "react";
import {
  unstable_useMentionAdapter,
  unstable_useSlashCommandAdapter,
  useAui,
} from "@assistant-ui/react";
import {
  copyMarkdownWithFallback,
  downloadMarkdown,
  serializeAssistantMarkdown,
  serializeThreadMarkdown,
  type TranscriptTurn,
} from "@digithings/digichat-ui";
import { DigichatThread, type ComposerLayout, type ThreadSlashTrigger } from "@digithings/web/chat/thread";
import {
  BASELINE_EMBED_PLACEHOLDER,
  BASELINE_EMBED_WELCOME,
} from "@/lib/baseline-embed";
import { useComposerCopy, useSkinChrome } from "@/components/stock/skin-chrome";
import { useStockComposerGateSubmit, useStockSendGate } from "@/components/stock/stock-send-gate";
import { useEmbedChatPrefsOptional } from "@/components/stock/embed-chat-prefs";
import {
  buildProductSlashCommands,
  extraSlashDefs,
  executeSlashDef,
  executeSlashFromComposer,
  prefixSlashAdapter,
  shouldInsertToolDraft,
  slashSubmitAction,
} from "@/lib/product-slash-commands";
import {
  armForceToolThenHold,
  setPendingForceTool,
  setPendingWebSearchForce,
} from "@/lib/pending-chat-headers";

/**
 * First-party digichat Thread. Explicit ThreadSkinView branch — never fall
 * through to product-page-assistant. Always left-aligned regardless of YAML.
 */
export function DigichatSkin({
  composerLayout,
}: {
  /** Explicit override — embed forces compact regardless of chrome mode. */
  composerLayout?: ComposerLayout;
}) {
  const { welcome, welcomeBody, placeholder } = useComposerCopy(
    BASELINE_EMBED_WELCOME,
    BASELINE_EMBED_PLACEHOLDER,
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
  const enableSlash = Boolean(slashPrefs);
  const extra = useMemo(
    () => (slashPrefs ? extraSlashDefs(slashPrefs) : []),
    [slashPrefs],
  );

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
      if (c.id === "compact") {
        return {
          ...c,
          execute: () => {
            const md = serializeThreadMarkdown(threadTurns(aui.thread().getState().messages));
            slashPrefs.reset();
            slashPrefs.newThread();
            if (!md.trim()) return;
            queueMicrotask(() => {
              aui.composer.setText(
                `Summarize this conversation so we can continue with a smaller context.\n\n${md}`,
              );
              aui.composer.send();
            });
          },
        };
      }
      if (c.id === "language") {
        return {
          ...c,
          execute: () =>
            executeSlashFromComposer(
              "lang",
              aui.composer.getState().text,
              slashPrefs,
              extra,
            ),
        };
      }
      if (c.id === "effort") {
        return {
          ...c,
          execute: () =>
            executeSlashFromComposer(
              "effort",
              aui.composer.getState().text,
              slashPrefs,
              extra,
            ),
        };
      }
      if (c.id === "byok") {
        return {
          ...c,
          execute: () =>
            executeSlashFromComposer(
              "byok",
              aui.composer.getState().text,
              slashPrefs,
              extra,
            ),
        };
      }
      if (c.id === "mcp") {
        return {
          ...c,
          execute: () =>
            executeSlashFromComposer(
              "mcp",
              aui.composer.getState().text,
              slashPrefs,
              extra,
            ),
        };
      }
      if (c.id === "tools") {
        return {
          ...c,
          execute: () =>
            executeSlashFromComposer(
              "tools",
              aui.composer.getState().text,
              slashPrefs,
              extra,
            ),
        };
      }
      if (shouldInsertToolDraft(c.id, extra)) {
        const draft = `${c.label?.startsWith("/") ? c.label : `/${c.id}`} `;
        return {
          ...c,
          execute: () => {
            queueMicrotask(() => aui.composer.setText(draft));
          },
        };
      }
      return c;
    });
  }, [enableSlash, slashPrefs, copyExport, aui, extra]);

  const slash = unstable_useSlashCommandAdapter({
    commands,
    removeOnExecute: true,
  });
  const slashTrigger = useMemo((): ThreadSlashTrigger => {
    return {
      adapter: prefixSlashAdapter(slash.adapter),
      action: slash.action,
    };
  }, [slash]);

  const mentionItems = useMemo(
    () =>
      (slashPrefs?.catalogTools ?? [])
        .filter((t) => t.id !== "web_search" || Boolean(slashPrefs?.tenantAllowsWeb))
        .map((t) => ({
          id: t.id,
          type: "tool",
          label: t.label?.trim() || t.id,
          description: `Use ${t.label?.trim() || t.id}`,
        })),
    [slashPrefs],
  );
  const mention = unstable_useMentionAdapter({
    items: mentionItems,
  });
  const mentionTrigger = useMemo(
    () =>
      mentionItems.length
        ? {
            adapter: mention.adapter,
            directive: mention.directive,
          }
        : undefined,
    [mention, mentionItems.length],
  );

  const onComposerSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      if (slashPrefs) {
        const text = aui.composer.getState().text;
        const action = slashSubmitAction(text, extra);
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
        if (action.kind === "force-web") {
          event.preventDefault();
          // Tenant-gated arm (#3871): a deny tenant (e.g. datatap) typing
          // /websearch must not set the pending flag — same tenantAllowsWeb
          // signal as the mention filter above. The BFF deny stays as backstop.
          if (slashPrefs.tenantAllowsWeb) {
            setPendingWebSearchForce(slashPrefs.sessionKey, true);
          }
          if (gate?.shouldHold(action.text)) {
            aui.composer.setText("");
            void aui.composer.clearAttachments();
            gate.onHold(action.text);
            return;
          }
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
    [slashPrefs, aui, gate, gateSubmit, copyExport, extra],
  );

  return (
    <DigichatThread
      welcome={welcome}
      welcomeBody={welcomeBody}
      placeholder={placeholder}
      onComposerSubmit={onComposerSubmit}
      composerLayout={composerLayout ?? (mode === "app" ? "expanded" : "compact")}
      slash={enableSlash ? slashTrigger : undefined}
      mention={enableSlash ? mentionTrigger : undefined}
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
