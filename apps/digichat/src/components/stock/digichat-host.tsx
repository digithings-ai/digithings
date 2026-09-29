"use client";

/**
 * Shared render host for the stock Thread (single-route plan, Step 1).
 *
 * ProductStockShell computes everything (config, chrome, boot lifecycle) and
 * delegates its render core here unchanged. Embed already renders through
 * ProductStockShell, so it renders through this host too. A catalog/minimal
 * mode (baseline) arrives in a later step.
 */

import type {
  ComponentProps,
  CSSProperties,
  ReactNode,
} from "react";
import {
  AssistantRuntimeProvider,
  RuntimeAdapterProvider,
  type AssistantRuntime,
} from "@assistant-ui/react";
import {
  ThreadSkinView,

} from "@digithings/ui/chat/skins";
import {
  StockSendGateProvider,
  DeployUiProvider,
  SkinChromeProvider,
  SkinRuntimeProvider,
  type StockSendGateHandlers,
  type DeployUiValue,
  type SkinChromeValue,
} from "@digithings/ui/chat/stock";
import type { ComposerLayout } from "@digithings/ui/chat/thread";
import {
  BootLabOverlay,
  type BootLabVariant,
} from "@digithings/ui/chat/boot-lab";
import { DigichatBootLoader } from "@digithings/ui/chat/boot-loader";
import type { DigichatHandoff } from "@digithings/ui/chat/boot-signal";
import type {
  DigichatClientConfig,
  DigichatClientFeatures,
} from "@/lib/deploy-config";
import type { ChainDisclosureMode } from "@/lib/view-modes";
import {
  parseEmbedChatError,
  formatEmbedChatError,
} from "@/lib/embed-chat-error";
import { DIGICHAT_SKIN_OPTIONS } from "@/lib/digichat-skin-options";
import { cn } from "@/lib/utils";
import { ToolCatalogBar } from "@/components/stock/tool-catalog-bar";
import { SessionPrefsToolBridge } from "@/components/stock/session-prefs-tool-bridge";
import type { ProductRuntimeAdapters } from "./product-shell";

/** Skin runtime for the catalog skins: same error copy as the direct import. */
const SKIN_RUNTIME = {
  errorParsers: {
    parseError: parseEmbedChatError,
    formatError: formatEmbedChatError,
  },
};

/** Hide reasoning / tool / source part UIs when features disable them. */
function FeatureCss({
  features,
  hideModelPicker,
  reasoningMode,
  toolCallsMode,
}: {
  features: DigichatClientFeatures;
  hideModelPicker: boolean;
  reasoningMode: ChainDisclosureMode;
  toolCallsMode: ChainDisclosureMode;
}) {
  const rules: string[] = [];
  if (reasoningMode === "off") {
    rules.push(
      '[data-stock-product] [data-slot="aui_reasoning"], [data-stock-product] .aui-reasoning-root { display: none !important; }',
    );
  }
  if (toolCallsMode === "off") {
    rules.push(
      '[data-stock-product] [data-slot="aui_tool-fallback"], [data-stock-product] .aui-tool-fallback-root { display: none !important; }',
    );
  }
  if (!features.sources) {
    rules.push(
      '[data-stock-product] [data-message-part-type^="source"], [data-stock-product] a[data-source] { display: none !important; }',
    );
  }
  if (!features.attachments) {
    rules.push(
      '[data-stock-product] [data-slot="aui_composer-add-attachment"], [data-stock-product] .aui-composer-add-attachment { display: none !important; }',
    );
  }
  if (!features.branchPicker) {
    rules.push(
      '[data-stock-product] [data-slot="aui_branch-picker"], [data-stock-product] .aui-branch-picker-root { display: none !important; }',
    );
  }
  if (hideModelPicker) {
    rules.push(
      "[data-stock-product] [data-deploy-model-picker] { display: none !important; }",
    );
  }
  if (rules.length === 0) return null;
  return <style dangerouslySetInnerHTML={{ __html: rules.join("\n") }} />;
}

export type DigiChatHostProps = {
  runtime: AssistantRuntime;
  auiConfig: ComponentProps<typeof AssistantRuntimeProvider>["config"];
  adapters: ProductRuntimeAdapters;
  sendGate: StockSendGateHandlers | null;
  clientConfig: DigichatClientConfig;
  features: DigichatClientFeatures;
  deployUi: DeployUiValue;
  skinChrome: SkinChromeValue;
  reasoningMode: ChainDisclosureMode;
  toolCallsMode: ChainDisclosureMode;
  view: string;
  thinking: string;
  mode: DigichatClientConfig["persistence"];
  headline: string;
  chips: readonly string[];
  inputPlaceholder: string;
  bootVisible: boolean;
  bootHidden: boolean;
  bootDone: boolean;
  bootReady: boolean;
  bootVariant: BootLabVariant | null;
  handoff: DigichatHandoff | null;
  handoffLive: boolean;
  bootRevealed: boolean;
  bootFacts: ComponentProps<typeof BootLabOverlay>["facts"];
  onBootSettled: () => void;
  accentStyle: CSSProperties | undefined;
  ownsPage: boolean;
  sideSlot: ReactNode;
  headerSlot: ReactNode;
  footerSlot: ReactNode;
  sessionKey?: string;
  webSearchScope?: string;
  onWebSearchChange?: (enabled: boolean) => void;
  className?: string;
  composerLayout?: ComposerLayout;
};

export function DigiChatHost({
  runtime,
  auiConfig,
  adapters,
  sendGate,
  clientConfig,
  features,
  deployUi,
  skinChrome,
  reasoningMode,
  toolCallsMode,
  view,
  thinking,
  mode,
  headline,
  chips,
  inputPlaceholder,
  bootVisible,
  bootHidden,
  bootDone,
  bootReady,
  bootVariant,
  handoff,
  handoffLive,
  bootRevealed,
  bootFacts,
  onBootSettled,
  accentStyle,
  ownsPage,
  sideSlot,
  headerSlot,
  footerSlot,
  sessionKey,
  webSearchScope,
  onWebSearchChange,
  className,
  composerLayout,
}: DigiChatHostProps) {
  return (
    <AssistantRuntimeProvider runtime={runtime} config={auiConfig}>
      <RuntimeAdapterProvider
        adapters={{
          ...(adapters.attachments ? { attachments: adapters.attachments } : {}),
        }}
      >
        <StockSendGateProvider handlers={sendGate}>
          <DeployUiProvider value={deployUi}>
            <SkinChromeProvider value={skinChrome}>
            <FeatureCss
              features={features}
              hideModelPicker={!skinChrome.modelPicker}
              reasoningMode={reasoningMode}
              toolCallsMode={toolCallsMode}
            />
            <SessionPrefsToolBridge />
            <div
              data-stock-product
              data-chrome-mode={clientConfig.chrome.mode}
              data-thread-skin={clientConfig.chrome.skin}
              data-persistence={mode}
              data-view={view}
              data-thinking={thinking}
              data-reasoning={reasoningMode}
              data-tool-calls={toolCallsMode}
              data-user-align={deployUi.userAlign}
              data-theme={clientConfig.chrome.theme}
              data-boot-reveal={bootRevealed && handoff?.reveal ? "true" : "false"}
              data-boot-drift={bootRevealed && handoff?.drift ? "true" : "false"}
              data-boot-active={bootVisible && !bootHidden ? "true" : "false"}
              className={cn(
                "relative flex h-full min-h-0 flex-1",
                sideSlot && !ownsPage ? "flex-row" : "flex-col",
                clientConfig.chrome.skin === "digichat" && "accent-digichat",
                className,
              )}
              style={accentStyle}
            >
              {!bootVisible || bootHidden ? null : (
                <div
                  className="dboot-overlay bg-background"
                  data-done={bootDone ? "true" : "false"}
                  data-instant={bootVariant && !handoffLive ? "true" : "false"}
                  data-drift={handoff?.drift ? "true" : "false"}
                >
                  {bootVariant ? (
                    <BootLabOverlay
                      variant={bootVariant}
                      ready={bootReady}
                      onSettled={onBootSettled}
                      accent={clientConfig.chrome.accent?.color}
                      facts={bootFacts}
                    />
                  ) : (
                    <DigichatBootLoader
                      ready={bootReady}
                      onSettled={onBootSettled}
                      welcome={headline}
                      welcomeBody={(skinChrome.welcomeBody ?? []).join(" ")}
                      suggestions={chips}
                      placeholder={inputPlaceholder}
                      accent={clientConfig.chrome.accent?.color}
                      showAttachment={features.attachments}
                    />
                  )}
                </div>
              )}
              {ownsPage ? null : sideSlot}
              <div
                className="relative flex min-h-0 min-w-0 flex-1 flex-col"

              >
                {ownsPage || clientConfig.chrome.skin === "digichat" ? null : headerSlot}
                {!ownsPage && sessionKey && clientConfig.chrome.mode === "app" ? (
                  <ToolCatalogBar
                    clientConfig={clientConfig}
                    sessionKey={sessionKey}
                    webSearchScope={webSearchScope}
                    onWebSearchChange={onWebSearchChange}
                  />
                ) : null}
                <div className="min-h-0 flex-1">
                  <SkinRuntimeProvider value={SKIN_RUNTIME}>
                    <ThreadSkinView
                      skin={clientConfig.chrome.skin}
                      composerLayout={composerLayout}
                      digichat={DIGICHAT_SKIN_OPTIONS}
                    />
                  </SkinRuntimeProvider>
                </div>
                {/* Placeholder attribute for stock composer — AuiConfig composer key varies by version */}
                <span className="sr-only" data-composer-placeholder={inputPlaceholder} />
                {/* The credit is not placed here: each skin's Thread renders it
                    in its own viewport footer, below the composer, so it tracks
                    the skin's canvas and can never be painted over (m2357).
                    `footerSlot` is still honoured for hosts (embed) that own
                    their own footer content. */}
                {footerSlot ?? null}
              </div>
            </div>
            </SkinChromeProvider>
          </DeployUiProvider>
        </StockSendGateProvider>
      </RuntimeAdapterProvider>
    </AssistantRuntimeProvider>
  );
}
