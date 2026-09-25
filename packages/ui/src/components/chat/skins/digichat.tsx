"use client";

import "../../../styles/chat-core.css";
import "../../../styles/chat-widgets.css";
import "../../../styles/chat-aui.css";
import "../../../styles/chat-digichat.css";
import "../../../styles/digichat-boot-loader.css";

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
} from "../transcript";
import {
  DigichatThread,
  type ComposerLayout,
  type ThreadSlashTrigger,
} from "../DigichatThread";

import {
  useComposerCopy,
  useSkinChrome,
} from "../stock/skin-chrome";
import { useDisclosureUi } from "../stock/deploy-ui-context";
import {
  useStockComposerGateSubmit,
  useStockSendGate,
} from "../stock/stock-send-gate";
import {
  useEmbedChatPrefsOptional,
  type EmbedChatPrefsApi,
} from "../stock/embed-chat-prefs";

/**
 * Product slash-command wiring injected by the host (WS4). Structural mirror
 * of the app's product-slash-commands + pending-headers signatures, so the
 * real app functions assign directly. The skin never imports app code.
 *
 * - `SkinSlashCommand` mirrors assistant-ui's `Unstable_SlashCommand`
 *   (`{ readonly id; label?; description?; icon?; execute: () => void }`).
 * - `SkinSlashExtraDef` mirrors the app's `SlashDef` minus `category`
 *   (optional-only there, so assignment holds both directions; runtime
 *   values are real app defs, and the skin never reads the extra fields).
 * - `SkinSlashAction` mirrors the app's `SlashSubmitAction` (`pass`, not `none`).
 */
export type SkinSlashCommand = {
  readonly id: string;
  readonly label?: string | undefined;
  readonly description?: string | undefined;
  readonly icon?: string | undefined;
  readonly execute: () => void;
};

export type SkinSlashExtraDef = {
  id: string;
  names: readonly string[];
  needsArg: boolean;
  hint: string;
  forceTool?: string;
  choiceOptions?: readonly { value: string; label: string }[];
  kind?: "toggle" | "action" | "tool" | "client";
};

export type SkinSlashAction =
  | { kind: "pass" }
  | { kind: "block" }
  | { kind: "force"; forceTool: string; text: string }
  | { kind: "force-web"; text: string }
  | { kind: "run"; command: SkinSlashExtraDef; arg: string };

/**
 * Structural mirror of the app's `SlashAdapterLike`
 * (`apps/digichat/src/lib/product-slash-commands.ts`). Identical shape keeps
 * the app's generic `prefixSlashAdapter` assignable to the prop below (WS4):
 * a constrained generic is only assignable to the same constraint.
 */
export type SkinSlashAdapterLike = {
  search?: (query: string) => readonly { id: string; label?: string }[];
  categories?: () => readonly { id: string; label: string }[];
  categoryItems?: (categoryId: string) => readonly unknown[];
};

export type DigichatSkinSlash = {
  buildCommands: (prefs: EmbedChatPrefsApi) => SkinSlashCommand[];
  extraDefs: (prefs: EmbedChatPrefsApi) => SkinSlashExtraDef[];
  prefixAdapter: <T extends SkinSlashAdapterLike>(inner: T) => T;
  shouldDraft: (id: string, extra: readonly SkinSlashExtraDef[]) => boolean;
  submitAction: (
    text: string,
    extra?: readonly SkinSlashExtraDef[],
  ) => SkinSlashAction;
  executeDef: (
    def: SkinSlashExtraDef,
    arg: string,
    prefs: EmbedChatPrefsApi,
  ) => void;
  executeFromComposer: (
    id: "lang" | "effort" | "byok" | "mcp" | "tools",
    composerText: string,
    prefs: EmbedChatPrefsApi,
    extra?: readonly SkinSlashExtraDef[],
  ) => void;
  armForceTool: (
    sessionKey: string,
    forceTool: string,
    onHold: () => void,
  ) => void;
  setForceTool: (sessionKey: string, forceTool?: string) => void;
  setWebSearchForce: (sessionKey: string, value: boolean) => void;
};

export type DigichatSkinCopy = {
  welcome?: string;
  placeholder?: string;
  suggestions?: readonly string[];
};

export type DigichatSkinOptions = {
  /** Explicit override — embed forces compact regardless of chrome mode. */
  composerLayout?: ComposerLayout;
  /** Welcome/placeholder/suggestion copy (host: BASELINE_EMBED_* constants). */
  copy?: DigichatSkinCopy;
  /**
   * Page-context attachment name (host: PAGE_CONTEXT_ATTACHMENT_NAME).
   * Protocol default mirrors the app literal ("page-context.html").
   */
  hiddenAttachmentName?: string;
  /** Product slash wiring; absent = slash/mention adapters stay disabled. */
  slash?: DigichatSkinSlash;
};

/**
 * First-party digichat Thread. Explicit ThreadSkinView branch — never fall
 * through to product-page-assistant. Always left-aligned regardless of YAML.
 */
/** Module-scope so it is a stable component reference, not recreated per render. */


export function DigichatSkin({
  composerLayout,
  copy,
  // Protocol default mirrors the app's PAGE_CONTEXT_ATTACHMENT_NAME
  // ("page-context.html"); hosts pass it explicitly.
  hiddenAttachmentName = "page-context.html",
  slash: slashWiring,
}: DigichatSkinOptions) {
  const { welcome, welcomeBody, placeholder, suggestions } = useComposerCopy(
    copy?.welcome ?? "",
    copy?.placeholder ?? "",
  );
  const { mode, pageContext } = useSkinChrome();
  const reasoningUi = useDisclosureUi("reasoning");
  const toolCallsUi = useDisclosureUi("toolCalls");
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
  const enableSlash = Boolean(slashPrefs) && Boolean(slashWiring);
  const extra = useMemo(
    () =>
      slashPrefs && slashWiring ? slashWiring.extraDefs(slashPrefs) : [],
    [slashPrefs, slashWiring],
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
    if (!enableSlash || !slashPrefs || !slashWiring) return [];
    return slashWiring.buildCommands(slashPrefs).map((c) => {
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
            slashWiring.executeFromComposer(
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
            slashWiring.executeFromComposer(
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
            slashWiring.executeFromComposer(
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
            slashWiring.executeFromComposer(
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
            slashWiring.executeFromComposer(
              "tools",
              aui.composer.getState().text,
              slashPrefs,
              extra,
            ),
        };
      }
      if (slashWiring.shouldDraft(c.id, extra)) {
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
  }, [enableSlash, slashPrefs, slashWiring, copyExport, aui, extra]);

  const slash = unstable_useSlashCommandAdapter({
    commands,
    removeOnExecute: true,
  });
  const slashTrigger = useMemo((): ThreadSlashTrigger => {
    return {
      adapter: slashWiring?.prefixAdapter(slash.adapter) ?? slash.adapter,
      action: slash.action,
    };
  }, [slash, slashWiring]);

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
      if (slashPrefs && slashWiring) {
        const text = aui.composer.getState().text;
        const action = slashWiring.submitAction(text, extra);
        if (action.kind === "block") {
          event.preventDefault();
          return;
        }
        if (action.kind === "force") {
          event.preventDefault();
          if (gate?.shouldHold(action.text)) {
            aui.composer.setText("");
            void aui.composer.clearAttachments();
            slashWiring.armForceTool(slashPrefs.sessionKey, action.forceTool, () => {
              gate.onHold(action.text);
            });
            return;
          }
          slashWiring.setForceTool(slashPrefs.sessionKey, action.forceTool);
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
            slashWiring.setWebSearchForce(slashPrefs.sessionKey, true);
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
          else slashWiring.executeDef(action.command, action.arg, slashPrefs);
          aui.composer.setText("");
          return;
        }
      }
      gateSubmit?.(event);
    },
    [slashPrefs, slashWiring, aui, gate, gateSubmit, copyExport, extra],
  );

  return (
    <DigichatThread
      welcome={welcome}
      welcomeBody={welcomeBody}
      suggestions={
        suggestions.length > 0 ? suggestions : (copy?.suggestions ?? [])
      }
      placeholder={placeholder}
      onComposerSubmit={onComposerSubmit}
      composerLayout={composerLayout ?? (mode === "app" ? "expanded" : "compact")}
      slash={enableSlash ? slashTrigger : undefined}
      mention={enableSlash ? mentionTrigger : undefined}
      hiddenAttachmentNames={
        pageContext === "silent" ? [hiddenAttachmentName] : undefined
      }
      reasoningMode={reasoningUi.mode}
      toolCallsMode={toolCallsUi.mode}

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
