"use client";

import { useMemo, useState } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/ai-sdk";
import { ThreadSkinView, type ThreadSkin } from "@digithings/ui/chat/skins";
import { DIGICHAT_SKIN_OPTIONS } from "@/lib/digichat-skin-options";
import {
  StockChatPrefsHost,
  useStockChatPrefs,
} from "@digithings/ui/chat/stock";
import {
  resolveRouteClientConfig,
  toStockChatPrefsConfig,
} from "@/lib/route-client-config";
import { p } from "@/lib/base-path";
import { cn } from "@/lib/utils";
import { SkinRuntimeProvider, SkinChromeProvider, type SkinChromeValue } from "@digithings/ui/chat/stock";
import { parseEmbedChatError, formatEmbedChatError } from "@/lib/embed-chat-error";
import { EmbedComposerMenu, type ComposerMenuKind } from "@/components/stock/embed-composer-menu";
import {
  connectedMcpConfigs,
  mcpSessionOverlayHeaderValue,
  replaceMcpConfig,
} from "@/components/stock/embed-mcp-flow";
import {
  DEFAULT_LANGUAGE_CODE,
  detectBrowserLanguageCode,
  tryResolveLanguageInput,
} from "@/lib/languages";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";

/** Stable no-ops: the preview has no persisted session to reset or redo. */
const noop = () => {};

// Unsaved-changes dot in the preview header.
const DIRTY_DOT_CLASS =
  "inline-block size-2 shrink-0 rounded-full bg-amber-500"; // canon-allow: dev-only status dot in the isolated devkit route (no token bridge), not product chrome

/** Same error copy as the product shell (mirrors baseline-client). */
const SKIN_RUNTIME = {
  errorParsers: {
    parseError: parseEmbedChatError,
    formatError: formatEmbedChatError,
  },
};

/** Same app functions the product shell passes (mirrors baseline-client). */
const PREFS_DEPS = {
  defaultLanguageCode: DEFAULT_LANGUAGE_CODE,
  detectLanguage: detectBrowserLanguageCode,
  resolveLanguage: tryResolveLanguageInput,
  mcpOps: {
    replace: replaceMcpConfig,
    connected: connectedMcpConfigs,
    headerValue: mcpSessionOverlayHeaderValue,
  },
  renderMenuPanes: (menu: {
    kind: ComposerMenuKind;
    models: readonly string[];
    providerSeed?: string;
    mcpSeed?: string;
    onClose: () => void;
  }) => (
    <EmbedComposerMenu
      kind={menu.kind}
      models={menu.models}
      onClose={menu.onClose}
      providerSeed={menu.providerSeed}
      mcpSeed={menu.mcpSeed}
    />
  ),
};

/**
 * Draft-driven preview: project the given (secret-stripped) deployment through
 * the same pure resolver the product route uses, then render its skin on the
 * dev BFF transport. The caller owns saved/draft knowledge — `deployment` is
 * already the last-valid draft state, `dirty` only toggles the unsaved dot,
 * and `issues` mirrors the same array the sidebar list renders (the bar
 * unmounts while valid). Mounted with a caller-chosen `key` (entry id +
 * skin/theme) so switching deployments — or changing skin/theme in the
 * draft — remounts cleanly.
 */
export function DevkitPreview({
  entryId,
  deployment,
  dirty = false,
  issues,
}: {
  entryId: string;
  deployment: DigichatDeployment;
  dirty?: boolean;
  issues: string[];
}) {
  const clientConfig = useMemo(
    () =>
      resolveRouteClientConfig({
        mode: "product",
        deployment: deployment as DigichatDeployment,
      }),
    [deployment],
  );
  const skin = clientConfig.chrome.skin;
  const [theme, setTheme] = useState<"dark" | "light">(clientConfig.chrome.theme);

  return (
    <DevkitPreviewInner
      key={entryId}
      slug={deployment.slug}
      skin={skin}
      theme={theme}
      dirty={dirty}
      issues={issues}
      onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      clientConfig={clientConfig}
      sessionKey={`devkit-${entryId}`}
    />
  );
}

function DevkitPreviewInner({
  slug,
  skin,
  theme,
  dirty,
  issues,
  onToggleTheme,
  clientConfig,
  sessionKey,
}: {
  slug: string;
  skin: ThreadSkin;
  theme: "dark" | "light";
  dirty: boolean;
  issues: string[];
  onToggleTheme: () => void;
  clientConfig: ReturnType<typeof resolveRouteClientConfig>;
  sessionKey: string;
}) {
  const runtime = useChatRuntime({
    transport: new AssistantChatTransport({
      api: p("/api/baseline-chat"),
      prepareSendMessagesRequest: ({ messages, body, headers }) => {
        const h = new Headers(headers as HeadersInit | undefined);
        h.set("X-Digi-Run-Id", crypto.randomUUID());
        return {
          body: {
            ...(typeof body === "object" && body !== null ? body : {}),
            messages,
          },
          headers: h,
        };
      },
    }),
  });

  const { prefsApi, panes } = useStockChatPrefs({
    config: toStockChatPrefsConfig(clientConfig),
    deps: PREFS_DEPS,
    sessionKey,
    hasSessions: false,
    newThread: noop,
    redo: noop,
  });

  // Live chrome copy: the same provider value the product shell builds from
  // its client config (mirrors product-shell), minus the embed URL-override
  // layer which doesn't exist in devkit. Every valid draft keystroke flows
  // text → validate → last-valid parsed → clientConfig → skins, with no
  // remount, so the chat transcript survives edits.
  const skinChrome = useMemo<SkinChromeValue>(
    () => ({
      skin,
      theme,
      mode: clientConfig.chrome.mode,
      title: clientConfig.chrome.title,
      welcome: clientConfig.chrome.welcome,
      welcomeBody: clientConfig.chrome.welcomeBody ?? [],
      placeholder: clientConfig.chrome.placeholder,
      suggestions: clientConfig.chrome.suggestions ?? [],
      accent: clientConfig.chrome.accent,
      modelPicker:
        toStockChatPrefsConfig(clientConfig).allowModelPicker ?? false,
      pageContext: clientConfig.features.pageContext,
      attribution: clientConfig.chrome.attribution,
    }),
    [skin, theme, clientConfig],
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div data-preview-slug={slug} className={cn("flex h-full flex-col", theme === "dark" && "dark")}>
        <div className="flex shrink-0 items-center gap-2 border-b px-3 py-1.5 text-xs text-muted-foreground">
          {dirty ? (
            <span
              aria-label="unsaved changes"
              title="unsaved changes"
              className={DIRTY_DOT_CLASS}
            />
          ) : null}
          <span className="font-mono">
            {slug} · {skin} · {theme}
            {clientConfig.models.default
              ? ` · ${clientConfig.models.default}`
              : " · no default model"}
          </span>
          <button
            type="button"
            onClick={onToggleTheme}
            className="ml-auto rounded-md px-2 py-1 hover:bg-accent"
          >
            {theme === "dark" ? "light" : "dark"}
          </button>
        </div>
        {issues.length > 0 ? (
          <div
            role="alert"
            data-testid="devkit-preview-invalid-bar"
            className="shrink-0 border-b border-destructive/50 px-3 py-1.5 font-mono text-[11px] text-destructive"
          >
            {issues.join(" ")}
          </div>
        ) : null}
        <div className="relative flex min-h-0 flex-1 flex-col bg-background text-foreground">
          <StockChatPrefsHost value={prefsApi} panes={panes}>
            <SkinRuntimeProvider value={SKIN_RUNTIME}>
              <SkinChromeProvider value={skinChrome}>
                <ThreadSkinView skin={skin} digichat={DIGICHAT_SKIN_OPTIONS} />
              </SkinChromeProvider>
            </SkinRuntimeProvider>
          </StockChatPrefsHost>
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
}
