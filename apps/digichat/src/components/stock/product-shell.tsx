"use client";

/**
 * Product surface: assistant-ui Thread (skin from deploy config) against POST /api/chat.
 * Feature flags / suggestions / chrome copy come from deployment client config.
 * Styling is the selected official assistant-ui template (`chrome.skin`).
 *
 * Every surface that rides this shell (embed, standalone, panels) also gets
 * the universal DigiChat boot animation: the loader mounts as an overlay
 * above the shell until it settles, then fades out and unmounts. The boot's
 * settle signal (see @digithings/ui chat/boot-signal) also releases copy
 * choreography that waits for it.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AuiConfig,
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  RuntimeAdapterProvider,
  SimpleImageAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  Suggestions,
  WebSpeechDictationAdapter,
  WebSpeechSynthesisAdapter,
  type AssistantRuntime,
  type AttachmentAdapter,
  type DictationAdapter,
  type SpeechSynthesisAdapter,
} from "@assistant-ui/react";
import { ThreadSkinView } from "@/components/assistant-ui/skins";
import type { ComposerLayout } from "@digithings/ui/chat/thread";
import {
  BootLabOverlay,
  resolveBootLabVariant,
  type BootLabVariant,
} from "@digithings/ui/chat/boot-lab";
import { DigichatBootLoader } from "@digithings/ui/chat/boot-loader";
import {
  DIGI_CHAT_READY_EVENT,
  hasDigichatReady,
  resolveHandoff,
  signalDigichatBootStep,
  signalDigichatRevealed,
  type DigichatHandoff,
} from "@digithings/ui/chat/boot-signal";
import type { DigichatClientConfig, DigichatClientFeatures } from "@/lib/deploy-config";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";
import {
  effectiveReasoningMode,
  effectiveToolCallsMode,
  type ChainDisclosureMode,
} from "@/lib/view-modes";
import { cn } from "@/lib/utils";
import { skinOwnsPageChrome } from "@/lib/thread-skins";
import { useEmbedChatPrefsOptional } from "@/components/stock/embed-chat-prefs";
import {
  StockSendGateProvider,
  type StockSendGateHandlers,
} from "@/components/stock/stock-send-gate";
import {
  DeployUiProvider,
  type DeployUiValue,
} from "@/components/stock/deploy-ui-context";
import {
  SkinChromeProvider,
  type SkinChromeValue,
} from "@/components/stock/skin-chrome";
import { ToolCatalogBar } from "@/components/stock/tool-catalog-bar";
import { SessionPrefsToolBridge } from "@/components/stock/session-prefs-tool-bridge";

/** Minimum cube sweep before the boot parks (keeps the contour visible). */
const BOOT_MIN_MS = 1400;
/** Overlay fade before the settled boot unmounts. */
const BOOT_FADE_MS = 320;

export type ProductShellProps = {
  runtime: AssistantRuntime;
  clientConfig?: DigichatClientConfig;
  /** Override welcome headline (URL ?welcome= wins in embed). */
  welcome?: string;
  suggestions?: readonly string[];
  placeholder?: string;
  className?: string;
  headerSlot?: ReactNode;
  footerSlot?: ReactNode;
  /** Rendered inside the runtime provider (e.g. memory thread list). */
  sideSlot?: ReactNode;
  /** Persistence mode — none|memory|server (server history is host-owned). */
  persistence?: DigichatClientConfig["persistence"];
  /**
   * Optional pre-send intercept (embed free-tier / BYOK hold). When shouldHold
   * returns true, Composer submit is swallowed and POST /api/chat is not fired.
   */
  sendGate?: StockSendGateHandlers | null;
  /**
   * Host / thread key for X-Digi-Force-Tool (must match takePendingForceTool).
   * When set and chrome.mode is `app`, tools.catalog renders above the Thread.
   * Embed / modal / sidebar use slash commands instead (#3733).
   */
  sessionKey?: string;
  /** localStorage scope for web search; defaults to sessionKey. */
  webSearchScope?: string;
  onWebSearchChange?: (enabled: boolean) => void;
  /** Explicit composer layout for the digichat skin (else mode-derived). */
  composerLayout?: ComposerLayout;
  /**
   * Boot-lab variant threaded from the embed server (local iteration). When
   * set, the overlay renders that alternate on first paint — no classic pass.
   */
  bootLabVariant?: string | null;
};

/** Adapters accepted by useAISDKRuntime / RuntimeAdapterProvider (attachments). */
export type ProductRuntimeAdapters = {
  attachments?: AttachmentAdapter;
  dictation?: DictationAdapter;
  speech?: SpeechSynthesisAdapter;
};

/** Build assistant-ui runtime adapters from deploy feature flags. */
export function buildProductRuntimeAdapters(
  features: DigichatClientFeatures,
): ProductRuntimeAdapters {
  const adapters: ProductRuntimeAdapters = {};
  if (features.attachments) {
    adapters.attachments = new CompositeAttachmentAdapter([
      new SimpleImageAttachmentAdapter(),
      new SimpleTextAttachmentAdapter(),
    ]);
  }
  if (features.dictation) {
    adapters.dictation = new WebSpeechDictationAdapter();
  }
  if (features.speech) {
    adapters.speech = new WebSpeechSynthesisAdapter();
  }
  return adapters;
}

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

/**
 * Mount the selected assistant-ui Thread with deploy-config adapters and chrome.
 * Caller owns AssistantChatTransport → POST /api/chat (never baseline-chat).
 *
 * Persistence:
 * - none → single thread (typical embed)
 * - memory → host passes useRemoteThreadListRuntime + sideSlot
 *   (SessionMemoryThreadListAdapter / ThreadListPrimitive sidebar)
 * - server → host uses ChatShell /api/conversations (auth session)
 */
export function ProductStockShell({
  runtime,
  persistence,
  clientConfig,
  welcome,
  suggestions,
  placeholder,
  className,
  headerSlot,
  footerSlot,
  sideSlot,
  sendGate = null,
  sessionKey,
  webSearchScope,
  onWebSearchChange,
  composerLayout,
  bootLabVariant,
}: ProductShellProps) {
  const cfg = clientConfig ?? DEFAULT_CLIENT_CONFIG;
  const features = cfg.features;
  const mode = persistence ?? cfg.persistence;
  const adapters = useMemo(() => buildProductRuntimeAdapters(features), [features]);
  const chatPrefs = useEmbedChatPrefsOptional();
  const view = chatPrefs?.prefs.view ?? features.view;
  const thinking = chatPrefs?.prefs.thinking ?? features.thinking;
  const reasoningMode = effectiveReasoningMode(view, thinking);
  const toolCallsMode = effectiveToolCallsMode(view);

  // Boot animation lifecycle: sweep, park after BOOT_MIN_MS, fade, unmount.
  // A document that already settled (soft navigation, warm container) starts
  // skipped: replaying the boot would flash the loader over a live chat.
  const bootAlreadyReady =
    typeof document !== "undefined" && hasDigichatReady();
  const [bootReady, setBootReady] = useState(bootAlreadyReady);
  const [bootDone, setBootDone] = useState(bootAlreadyReady);
  const [bootHidden, setBootHidden] = useState(bootAlreadyReady);
  // Set when the boot is skipped (already-settled document or an instant
  // ready) so the handoff choreography stays off too - nothing should replay.
  const bootSkippedRef = useRef(bootAlreadyReady);
  // The boot UI renders client-side only, after the skip window: an instant
  // ready means there is nothing to load, and a warm refresh must not flash
  // the chain before the skip lands. Lab knobs show it immediately.
  const [bootVisible, setBootVisible] = useState(false);
  // The tool-chain boot is the baseline now; `?boot=` still overrides it.
  const [bootVariant, setBootVariant] = useState<BootLabVariant | null>(() =>
    resolveBootLabVariant(bootLabVariant ?? null) ?? "tooltask",
  );

  // Transition lab switch: `?handoff=` picks how the boot hands off to the
  // chat (reveal / type / drift / beat). Resolved after mount so the SSR
  // markup never depends on the URL.
  const [handoff, setHandoff] = useState<DigichatHandoff | null>(null);

  // Handoff demos must show the real crossfade (the lab boot ordinarily skips
  // the fade with data-instant + an instant unmount).
  const handoffLive = Boolean(
    handoff && (handoff.reveal || handoff.type || handoff.drift || handoff.beat),
  );

  // The bottom-up entrance plays on every load - skipped boots included:
  // the hero should always build up from the composer, never cut in.
  // Derived from bootDone rather than a state flip in an effect
  // (react-hooks/set-state-in-effect).
  const bootRevealed = bootDone;

  useEffect(() => {
    const timer = setTimeout(() => setBootReady(true), BOOT_MIN_MS);
    return () => clearTimeout(timer);
  }, []);

  // Ready that lands almost immediately (warm container) means the chat was
  // not really loading: skip the choreography instead of replaying it.
  // Lab knobs (?boot=/?bootdelay=/?bootfail=/?handoff=/?hero=) keep the boot
  // visible for demos even on warm loads.
  useEffect(() => {
    if (bootDone) return;
    if (/[?&](boot|bootdelay|bootfail|handoff|hero)=/.test(window.location.search)) {
      return;
    }
  if (hasDigichatReady()) {
    bootSkippedRef.current = true;
    // Defer setState out of the synchronous effect body -
    // react-hooks/set-state-in-effect.
    queueMicrotask(() => {
      setBootDone(true);
      setBootHidden(true);
    });
    return;
  }
    const startedAt = performance.now();
    const onReady = () => {
      if (performance.now() - startedAt <= 600) {
        bootSkippedRef.current = true;
        setBootDone(true);
        setBootHidden(true);
      }
    };
    window.addEventListener(DIGI_CHAT_READY_EVENT, onReady, { once: true });
    return () => window.removeEventListener(DIGI_CHAT_READY_EVENT, onReady);
  }, [bootDone]);

  useEffect(() => {
    if (bootHidden) return;
  if (/[?&](boot|bootdelay|bootfail|handoff|hero)=/.test(window.location.search)) {
    // Defer setState out of the synchronous effect body -
    // react-hooks/set-state-in-effect.
    queueMicrotask(() => setBootVisible(true));
    return;
  }
    const timer = setTimeout(() => setBootVisible(true), 600);
    return () => clearTimeout(timer);
  }, [bootHidden]);

  useEffect(() => {
    if (!bootDone) return;
    const timer = setTimeout(
      () => setBootHidden(true),
      bootVariant && !handoffLive ? 0 : BOOT_FADE_MS,
    );
    return () => clearTimeout(timer);
  }, [bootDone, bootVariant, handoffLive]);

  // Boot-lab switch: `?boot=<variant>` swaps the classic choreography for a
  // short alternate (local iteration only; unknown values keep classic).
  // The embed route threads the value from the server so the classic loader
  // never paints first (the outline bleed); the URL fallback covers surfaces
  // that mount without the prop. Resolved once in the state initializer above
  // (no effect needed: react-hooks/set-state-in-effect).

  useEffect(() => {
    // Defer setState out of the synchronous effect body -
    // react-hooks/set-state-in-effect.
    queueMicrotask(() => setHandoff(resolveHandoff()));
  }, []);

  // The overlay starts fading: release the handoff choreography (hero
  // re-entry, welcome takeover) and let listeners know.
  useEffect(() => {
    if (!bootDone) return;
    signalDigichatRevealed();
  }, [bootDone]);

  // Real boot milestone: the product shell mounted with its chat runtime.
  useEffect(() => {
    signalDigichatBootStep("runtime");
  }, []);

  const deployUi = useMemo<DeployUiValue>(
    () => ({
      reasoning: reasoningMode,
      toolCalls: toolCallsMode,
      userAlign:
        cfg.chrome.skin === "digichat" ? "left" : cfg.chrome.transcript.userAlign,
    }),
    [reasoningMode, toolCallsMode, cfg.chrome.skin, cfg.chrome.transcript.userAlign],
  );

  const skinChrome = useMemo<SkinChromeValue>(
    () => ({
      skin: cfg.chrome.skin,
      theme: cfg.chrome.theme,
      mode: cfg.chrome.mode,
      title: cfg.chrome.title,
      welcome: welcome?.trim() || cfg.chrome.welcome,
      welcomeBody: cfg.chrome.welcomeBody ?? [],
      placeholder: placeholder?.trim() || cfg.chrome.placeholder,
      suggestions: (suggestions?.length ? suggestions : cfg.chrome.suggestions) ?? [],
      accent: cfg.chrome.accent,
      modelPicker: features.modelPicker || cfg.models.allowPicker,
      pageContext: features.pageContext,
    }),
    [
      cfg.chrome.skin,
      cfg.chrome.theme,
      cfg.chrome.mode,
      cfg.chrome.title,
      cfg.chrome.welcome,
      cfg.chrome.welcomeBody,
      cfg.chrome.placeholder,
      cfg.chrome.suggestions,
      cfg.chrome.accent,
      features.modelPicker,
      features.pageContext,
      cfg.models.allowPicker,
      welcome,
      placeholder,
      suggestions,
    ],
  );

  const headline =
    welcome?.trim() ||
    cfg.chrome.welcome?.trim() ||
    cfg.chrome.title?.trim() ||
    "How can I help you today?";
  const chips = (suggestions?.length ? suggestions : cfg.chrome.suggestions) ?? [];
  const inputPlaceholder =
    placeholder?.trim() || cfg.chrome.placeholder || "Send a message...";

  // Real deployment facts for the boot chain - the same values the chat runs
  // on, so the loader never claims counts the deployment does not have.
  const bootFacts = useMemo(
    () => ({
      starters: skinChrome.suggestions.length,
      model: cfg.models.default,
      models: cfg.models.available.length,
      toolLabels: cfg.tools.catalog.map((tool) => tool.label ?? tool.id),
      mcpServers: cfg.mcp.servers.length,
      backend: cfg.backendType,
    }),
    [
      skinChrome.suggestions,
      cfg.models.default,
      cfg.models.available,
      cfg.tools.catalog,
      cfg.mcp.servers,
      cfg.backendType,
    ],
  );

  const auiConfig = useMemo(
    () =>
      AuiConfig({
        ...(chips.length > 0 ? { suggestions: Suggestions([...chips]) } : {}),
      }),
    [chips],
  );

  const ownsPage = skinOwnsPageChrome(cfg.chrome.skin);
  const accentStyle = cfg.chrome.accent
    ? ({
        ["--accent" as string]: cfg.chrome.accent.color,
        ["--accent-foreground" as string]: cfg.chrome.accent.foreground,
      } as const)
    : undefined;

  // Beat handoff: hold the settled frame (the final check) a beat longer
  // before the fade starts.
  const onBootSettled = () => {
    if (handoff?.beat) {
      setTimeout(() => setBootDone(true), 220);
      return;
    }
    setBootDone(true);
  };

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
              data-chrome-mode={cfg.chrome.mode}
              data-thread-skin={cfg.chrome.skin}
              data-persistence={mode}
              data-view={view}
              data-thinking={thinking}
              data-reasoning={reasoningMode}
              data-tool-calls={toolCallsMode}
              data-user-align={deployUi.userAlign}
              data-theme={cfg.chrome.theme}
              data-boot-reveal={bootRevealed && handoff?.reveal ? "true" : "false"}
              data-boot-drift={bootRevealed && handoff?.drift ? "true" : "false"}
              data-boot-active={bootVisible && !bootHidden ? "true" : "false"}
              className={cn(
                "relative flex h-full min-h-0 flex-1",
                sideSlot && !ownsPage ? "flex-row" : "flex-col",
                cfg.chrome.skin === "digichat" && "accent-digichat",
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
                      accent={cfg.chrome.accent?.color}
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
                      accent={cfg.chrome.accent?.color}
                      showAttachment={features.attachments}
                    />
                  )}
                </div>
              )}
              {ownsPage ? null : sideSlot}
              <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                {ownsPage || cfg.chrome.skin === "digichat" ? null : headerSlot}
                {!ownsPage && sessionKey && cfg.chrome.mode === "app" ? (
                  <ToolCatalogBar
                    clientConfig={cfg}
                    sessionKey={sessionKey}
                    webSearchScope={webSearchScope}
                    onWebSearchChange={onWebSearchChange}
                  />
                ) : null}
                <div className="min-h-0 flex-1">
                  <ThreadSkinView
                    skin={cfg.chrome.skin}
                    welcome={headline}
                    composerLayout={composerLayout}
                  />
                </div>
                {footerSlot}
                {/* Placeholder attribute for stock composer — AuiConfig composer key varies by version */}
                <span className="sr-only" data-composer-placeholder={inputPlaceholder} />
              </div>
            </div>
            </SkinChromeProvider>
          </DeployUiProvider>
        </StockSendGateProvider>
      </RuntimeAdapterProvider>
    </AssistantRuntimeProvider>
  );
}
