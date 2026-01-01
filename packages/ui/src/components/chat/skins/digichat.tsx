"use client";

import "../../../styles/chat-core.css";
import "../../../styles/chat-widgets.css";
import "../../../styles/chat-aui.css";
import "../../../styles/chat-digichat.css";
import "../../../styles/digichat-boot-loader.css";

import { useCallback, type FormEvent } from "react";
import {
  DigichatThread,
  type ComposerLayout,
} from "../DigichatThread";

import {
  useComposerCopy,
  useSkinChrome,
} from "../stock/skin-chrome";
import {
  useDeployUi,
  useDisclosureUi,
} from "../stock/deploy-ui-context";
import { workVisibilityForView } from "../stock/skin-types";
import { useStockComposerGateSubmit } from "../stock/stock-send-gate";
import { useEmbedChatPrefsOptional } from "../stock/embed-chat-prefs";
import {
  useSkinSlashPalette,
  type DigichatSkinSlash,
} from "../stock/skin-slash-palette";
import { DigichatComposerToolbar } from "./digichat-composer-toolbar";

// The slash wiring types moved to the skin-agnostic palette module; the
// re-export keeps `@digithings/ui/chat/skins` imports unchanged.
export type {
  DigichatSkinSlash,
  SkinPaletteApply,
  SkinPaletteFrame,
  SkinPaletteKind,
  SkinSlashAction,
  SkinSlashAdapterLike,
  SkinSlashCommand,
  SkinSlashExtraDef,
} from "../stock/skin-slash-palette";

export type DigichatSkinCopy = {
  welcome?: string;
  placeholder?: string;
  suggestions?: readonly string[];
};

export type DigichatSkinOptions = {
  /**
   * Explicit override — a deployment can still force compact regardless of
   * chrome mode. Omitted means the expanded composer everywhere.
   */
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
  /**
   * Private session, set per session by the host. Hides reasoning text and
   * tool-call output and shows the mode badge. Display-only: the model still
   * produces the work, and the stores still hold the real text.
   */
  privateMode?: boolean;
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
  privateMode,
}: DigichatSkinOptions) {
  const { welcome, welcomeBody, placeholder, suggestions } = useComposerCopy(
    copy?.welcome ?? "",
    copy?.placeholder ?? "",
  );
  const skinChrome = useSkinChrome();
  const { pageContext } = skinChrome;
  const reasoningUi = useDisclosureUi("reasoning");
  const toolCallsUi = useDisclosureUi("toolCalls");
  // The raw view level is what decides how much of the work is shown.
  const deployUi = useDeployUi();
  const workVisibility = workVisibilityForView(deployUi.view);
  const gateSubmit = useStockComposerGateSubmit();
  const prefs = useEmbedChatPrefsOptional();
  // The `/` palette logic is shared with every other skin (SkinPaletteBridge).
  const palette = useSkinSlashPalette({ slash: slashWiring, privateMode });
  const paletteSubmit = palette.handleSubmit;

  const onComposerSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      if (paletteSubmit(event)) return;
      gateSubmit?.(event);
    },
    [paletteSubmit, gateSubmit],
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
      composerLayout={composerLayout ?? "expanded"}
      slash={palette.slash}
      mention={palette.mention}
      hiddenAttachmentNames={
        pageContext === "silent" ? [hiddenAttachmentName] : undefined
      }
      reasoningMode={reasoningUi.mode}
      toolCallsMode={toolCallsUi.mode}
      workVisibility={workVisibility}
      privateMode={privateMode}
      composerToolbar={
        prefs && prefs.prefs.toolbar !== false ? (
          <DigichatComposerToolbar prefs={prefs} />
        ) : undefined
      }
      scrollbars={prefs?.prefs.scrollbars ?? "always"}
      scrollMode={prefs?.prefs.scroll}
      density={prefs?.prefs.density ?? "default"}
    />
  );
}
