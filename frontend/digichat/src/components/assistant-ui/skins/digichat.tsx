"use client";

import "@digithings/web/styles/chat-core.css";
import "@digithings/web/styles/chat-widgets.css";
import "@digithings/web/styles/chat-aui.css";
import "@digithings/web/styles/chatbot.css";

import { DigichatThread } from "@digithings/web/chat/thread";
import { useComposerCopy } from "@/components/stock/skin-chrome";
import { useStockComposerGateSubmit } from "@/components/stock/stock-send-gate";

/**
 * First-party digichat Thread. Explicit ThreadSkinView branch — never fall
 * through to product-page-assistant. Always left-aligned regardless of YAML.
 */
export function DigichatSkin() {
  const { welcome, welcomeBody, placeholder } = useComposerCopy(
    "What should we inspect?",
    "Ask digichat…",
  );
  const onComposerSubmit = useStockComposerGateSubmit();
  return (
    <DigichatThread
      welcome={welcome}
      welcomeBody={welcomeBody}
      placeholder={placeholder}
      onComposerSubmit={onComposerSubmit}
    />
  );
}
