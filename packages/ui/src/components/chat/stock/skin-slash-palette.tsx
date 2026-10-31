"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  unstable_useMentionAdapter,
  unstable_useSlashCommandAdapter,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import {
  copyMarkdownWithFallback,
  serializeAssistantMarkdown,
  serializeThreadMarkdown,
  transcriptTurns,
  type ChatExportFormat,
} from "../transcript";
import type {
  ThreadMentionTrigger,
  ThreadSlashTrigger,
} from "../gallery-thread/thread.aui";
import { useStockSendGate } from "./stock-send-gate";
import {
  useEmbedChatPrefsOptional,
  type EmbedChatPrefsApi,
} from "./embed-chat-prefs";
import { exportConversation } from "../../../replay/chat-export-run";
import { applyExportSlash } from "../../../replay/export-format";
import { useChatExportStrings } from "./message-export-menu";

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
  | { kind: "pane"; command: SkinSlashExtraDef; arg: string }
  | { kind: "run"; command: SkinSlashExtraDef; arg: string };

export type SkinPaletteKind = "closed" | "commands" | "pane";

export type SkinPaletteFrame = {
  kind: SkinPaletteKind;
  filter?: string;
  menu?: string;
};

export type SkinPaletteApply = {
  kind: SkinPaletteKind;
  menu: "close" | "keep" | string;
  filter: string;
};

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
  /** Composer text → the one open surface. */
  frame: (text: string) => SkinPaletteFrame;
  /** Previous surface plus the next frame. A button-opened menu can stay. */
  applyFrame: (prev: SkinPaletteKind, frame: SkinPaletteFrame) => SkinPaletteApply;
  /** Draft written when a pane command is chosen (`/language `), or null. */
  paneDraft: (id: string) => string | null;
  armForceTool: (
    sessionKey: string,
    forceTool: string,
    onHold: () => void,
  ) => void;
  setForceTool: (sessionKey: string, forceTool?: string) => void;
  setWebSearchForce: (sessionKey: string, value: boolean) => void;
};

/** The product `/` palette, independent of the skin that renders it. */
export type SkinSlashPalette = {
  /** True when the host passed slash wiring and mounted the prefs host. */
  enabled: boolean;
  /** `/` trigger for a composer popover; undefined when disabled. */
  slash: ThreadSlashTrigger | undefined;
  /** `@` tool trigger; undefined when disabled or the catalog is empty. */
  mention: ThreadMentionTrigger | undefined;
  /**
   * Runs the slash submit action for the composer text. Returns true when the
   * palette consumed the submit (block, pane, force, run); the caller must
   * then not send. False means a plain message: the skin sends as usual.
   */
  handleSubmit: (event: { preventDefault(): void }) => boolean;
};

export type SkinSlashPaletteOptions = {
  slash?: DigichatSkinSlash | undefined;
  /** Rebuilds the rows when the private session flips (`/private` value). */
  privateMode?: boolean | undefined;
};

/**
 * Product slash-command palette logic shared by every skin. The digichat skin
 * hands the result to its own composer; every other skin gets it through
 * `SkinPaletteBridge`. Moved verbatim from the digichat skin.
 */
export function useSkinSlashPalette({
  slash: slashWiring,
  privateMode,
}: SkinSlashPaletteOptions): SkinSlashPalette {
  const gate = useStockSendGate();
  const prefs = useEmbedChatPrefsOptional();
  const aui = useAui();
  const composerText = useAuiState((s) => s.composer.text);
  const palettePrev = useRef<SkinPaletteKind>("closed");
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
  useEffect(() => {
    if (!enableSlash || !slashPrefs?.syncPalette || !slashWiring) return;
    const next = slashWiring.applyFrame(palettePrev.current, slashWiring.frame(composerText));
    palettePrev.current = next.kind;
    slashPrefs.syncPalette(next);
  }, [composerText, enableSlash, slashPrefs, slashWiring]);
  useEffect(() => {
    if (!slashPrefs?.bindComposerDraft) return;
    slashPrefs.bindComposerDraft((text) => {
      aui.composer.setText(text);
    });
  }, [slashPrefs, aui]);
  const extra = useMemo(
    () =>
      slashPrefs && slashWiring ? slashWiring.extraDefs(slashPrefs) : [],
    [slashPrefs, slashWiring],
  );

  const exportStrings = useChatExportStrings();
  const copyExport = useMemo(
    () => ({
      copy: () => {
        const turns = transcriptTurns(aui.thread().getState().messages);
        const last = [...turns].reverse().find((t) => t.role === "assistant");
        if (!last) return;
        void copyMarkdownWithFallback(serializeAssistantMarkdown(last.content, last.sources));
      },
      /** The whole conversation, from the chat menu or a typed `/export md|html`. */
      exportConversation: (format: ChatExportFormat) => {
        if (privateMode) return;
        void exportConversation({
          format,
          privateMode,
          messages: aui.thread().getState().messages,
          strings: exportStrings,
        });
      },
    }),
    [aui, exportStrings, privateMode],
  );
  // The settings menu and the `/export` pane live outside the runtime; they
  // reach the thread through the prefs host.
  useEffect(() => {
    if (!slashPrefs?.bindThreadExport) return;
    slashPrefs.bindThreadExport(copyExport.exportConversation);
  }, [slashPrefs, copyExport]);

  const commands = useMemo(() => {
    if (!enableSlash || !slashPrefs || !slashWiring) return [];
    return slashWiring.buildCommands(slashPrefs).map((c) => {
      if (c.id === "copy") return { ...c, execute: copyExport.copy };
      if (c.id === "compact") {
        return {
          ...c,
          execute: () => {
            const md = serializeThreadMarkdown(transcriptTurns(aui.thread().getState().messages));
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
      const draft = slashWiring.paneDraft(c.id);
      if (draft) {
        return {
          ...c,
          execute: () => {
            queueMicrotask(() => aui.composer.setText(draft));
          },
        };
      }
      if (slashWiring.shouldDraft(c.id, extra)) {
        const inserted = `${c.label?.startsWith("/") ? c.label : `/${c.id}`} `;
        return {
          ...c,
          execute: () => {
            queueMicrotask(() => aui.composer.setText(inserted));
          },
        };
      }
      return c;
    });
    // `privateMode` is read inside `buildCommands` (the `/private` row's
    // value) from a store, not from an argument: listing it here rebuilds the
    // rows when it flips, so the palette shows the current value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enableSlash, slashPrefs, slashWiring, copyExport, aui, extra, privateMode]);

  const slash = unstable_useSlashCommandAdapter({
    commands,
    removeOnExecute: true,
  });
  const slashTrigger = useMemo((): ThreadSlashTrigger => {
    return {
      adapter: slashWiring?.prefixAdapter(slash.adapter) ?? slash.adapter,
      action: slash.action,
      matcher: (text, _triggerChar, cursorPosition) => {
        if (!slashWiring || cursorPosition <= 0) return null;
        const frame = slashWiring.frame(text);
        if (frame.kind !== "commands") return null;
        return { query: frame.filter ?? "", offset: 0, endOffset: cursorPosition };
      },
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

  const handleSubmit = useCallback(
    (event: { preventDefault(): void }): boolean => {
      if (slashPrefs && slashWiring) {
        const text = aui.composer.getState().text;
        const action = slashWiring.submitAction(text, extra);
        if (action.kind === "block" || action.kind === "pane") {
          event.preventDefault();
          return true;
        }
        if (action.kind === "force") {
          event.preventDefault();
          if (gate?.shouldHold(action.text)) {
            aui.composer.setText("");
            void aui.composer.clearAttachments();
            slashWiring.armForceTool(slashPrefs.sessionKey, action.forceTool, () => {
              gate.onHold(action.text);
            });
            return true;
          }
          slashWiring.setForceTool(slashPrefs.sessionKey, action.forceTool);
          aui.composer.setText(action.text);
          gate?.onAllowSend?.();
          aui.composer.send();
          return true;
        }
        if (action.kind === "force-web") {
          event.preventDefault();
          // Tenant-gated arm (#3871): a deny tenant typing
          // /websearch must not set the pending flag — same tenantAllowsWeb
          // signal as the mention filter above. The BFF deny stays as backstop.
          if (slashPrefs.tenantAllowsWeb) {
            slashWiring.setWebSearchForce(slashPrefs.sessionKey, true);
          }
          if (gate?.shouldHold(action.text)) {
            aui.composer.setText("");
            void aui.composer.clearAttachments();
            gate.onHold(action.text);
            return true;
          }
          aui.composer.setText(action.text);
          gate?.onAllowSend?.();
          aui.composer.send();
          return true;
        }
        if (action.kind === "run") {
          event.preventDefault();
          if (action.command.id === "copy") copyExport.copy();
          else if (action.command.id === "export") {
            applyExportSlash(action.arg, document, {
              html: () => copyExport.exportConversation("html"),
              markdown: () => copyExport.exportConversation("md"),
            });
          }
          else if (action.command.id === "compact") {
            // Palette compact serializes the thread and queues a summary.
            // executeDef only resets prefs and opens an empty thread.
            const compact = commands.find((command) => command.id === "compact");
            if (compact) compact.execute();
            else slashWiring.executeDef(action.command, action.arg, slashPrefs);
          } else slashWiring.executeDef(action.command, action.arg, slashPrefs);
          aui.composer.setText("");
          return true;
        }
      }
      return false;
    },
    [slashPrefs, slashWiring, aui, gate, copyExport, extra, commands],
  );

  return useMemo(
    () => ({
      enabled: enableSlash,
      slash: enableSlash ? slashTrigger : undefined,
      mention: enableSlash ? mentionTrigger : undefined,
      handleSubmit,
    }),
    [enableSlash, slashTrigger, mentionTrigger, handleSubmit],
  );
}


