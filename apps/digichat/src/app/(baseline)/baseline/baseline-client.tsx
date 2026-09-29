"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/ai-sdk";
import { ThreadSkinView } from "@digithings/ui/chat/skins";
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
import {
  parseThreadSkin,

  THREAD_SKINS,
} from "@digithings/ui/chat/skins";
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

/** Stable no-ops: the catalog has no persisted session to reset or redo. */
const noop = () => {};

/** Skin runtime: the catalog gets the same error copy as the product shell. */
const SKIN_RUNTIME = {
  errorParsers: {
    parseError: parseEmbedChatError,
    formatError: formatEmbedChatError,
  },
};

/** Prefs deps: the same app functions the product shell passes (WS4 Step 3). */
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
 * Official assistant-ui templates (the 11 catalog ids) plus first-party
 * `digichat`. Transport is the localhost baseline BFF, which proxies production
 * digithings.ai/api/chat (Cloudflare stack).
 *
 * `?skin=base|chatgpt|claude|grok|gemini|perplexity|react-ink|expo-react-native|base-assistant-ui|webpage-assistant|product-page-assistant|digichat`
 * `?theme=dark|light`
 */
export function BaselineClient() {
  return (
    <Suspense fallback={null}>
      <BaselineClientInner />
    </Suspense>
  );
}

function BaselineClientInner() {
  const searchParams = useSearchParams();
  const skin = parseThreadSkin(searchParams.get("skin"));
  const theme = searchParams.get("theme") === "dark" ? "dark" : "light";

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

  // The first-party skin's light palette hangs off `:root[data-theme="light"]`
  // and `.light` (chat-aui.css), and its portal mirrors off
  // `html.light:has(...)`. Without this the skin always renders its dark
  // palette, so "light" mode looked like a dark theme.
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.classList.toggle("light", theme === "light");
    root.classList.toggle("dark", theme === "dark");
  }, [theme]);

  // The `digichat` skin's `/` command palette and @-mention menu are gated on the
  // embed chat prefs (`useEmbedChatPrefsOptional`). Mount the same prefs host the
  // embed/product shells use, with the least-privilege default config, so the
  // catalog renders the same composer chrome as digithings.ai/chat instead of
  // each surface having to re-implement the gate. Other catalog skins ignore it.
  const { prefsApi, panes } = useStockChatPrefs({
    config: toStockChatPrefsConfig(resolveRouteClientConfig({ mode: "catalog" })),
    deps: PREFS_DEPS,
    sessionKey: "baseline",
    hasSessions: false,
    newThread: () => {},
    redo: () => {},
  });

  const hrefFor = (nextSkin: string, nextTheme: string) => {
    const qs = new URLSearchParams();
    if (nextSkin !== "base") qs.set("skin", nextSkin);
    if (nextTheme === "dark") qs.set("theme", "dark");
    const query = qs.toString();
    return query ? `/baseline?${query}` : "/baseline";
  };

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className={cn("flex h-dvh flex-col", theme === "dark" && "dark")}>
        <nav
          aria-label="assistant-ui templates"
          className="flex shrink-0 flex-wrap items-center gap-1 border-b border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-black dark:text-zinc-400"
        >
          {THREAD_SKINS.map((id) => {
            const href = hrefFor(id, theme);
            const active = skin === id;
            return (
              <a
                key={id}
                href={href}
                className={cn(
                  "rounded-md px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-900",
                  active && "bg-zinc-100 font-medium text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100",
                )}
              >
                {id}
              </a>
            );
          })}
          <a
            href={hrefFor(skin, theme === "dark" ? "light" : "dark")}
            className="ml-auto rounded-md px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-900"
          >
            {theme === "dark" ? "light" : "dark"}
          </a>
        </nav>
        {/* Thread canvas wrapper. */}
        <div
          className="relative flex min-h-0 flex-1 flex-col bg-background text-foreground"

        >
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
