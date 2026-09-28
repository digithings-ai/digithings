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
import { SkinRuntimeProvider } from "@digithings/ui/chat/stock";
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
 * already the last-valid draft state and `dirty` only toggles the unsaved dot.
 * Mounted with a caller-chosen `key` (entry id + skin/theme) so switching
 * deployments — or changing skin/theme in the draft — remounts cleanly.
 */
export function DevkitPreview({
  entryId,
  deployment,
  dirty = false,
}: {
  entryId: string;
  deployment: DigichatDeployment;
  dirty?: boolean;
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
      skin={skin}
      theme={theme}
      dirty={dirty}
      onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      clientConfig={clientConfig}
      sessionKey={`devkit-${entryId}`}
    />
  );
}

function DevkitPreviewInner({
  skin,
  theme,
  dirty,
  onToggleTheme,
  clientConfig,
  sessionKey,
}: {
  skin: ThreadSkin;
  theme: "dark" | "light";
  dirty: boolean;
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

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className={cn("flex h-full flex-col", theme === "dark" && "dark")}>
        <div className="flex shrink-0 items-center gap-2 border-b px-3 py-1.5 text-xs text-muted-foreground">
          {dirty ? (
            <span
              aria-label="unsaved changes"
              title="unsaved changes"
              className="inline-block size-2 shrink-0 rounded-full bg-amber-500"
            />
          ) : null}
          <span className="font-mono">
            {skin} · {theme}
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
        <div className="relative flex min-h-0 flex-1 flex-col bg-background text-foreground">
          <StockChatPrefsHost value={prefsApi} panes={panes}>
            <SkinRuntimeProvider value={SKIN_RUNTIME}>
              <ThreadSkinView skin={skin} digichat={DIGICHAT_SKIN_OPTIONS} />
            </SkinRuntimeProvider>
          </StockChatPrefsHost>
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
}
