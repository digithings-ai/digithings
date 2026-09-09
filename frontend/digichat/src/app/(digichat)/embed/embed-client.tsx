"use client";

/**
 * /embed — minimal unauthenticated chat surface for iframe embedding.
 *
 *   ?accent=digithings|digiquant|digichat   (default: digichat)
 *   ?host=<the embedding page's own origin> — see resolveEmbedHost() (#1372)
 *   ?token=<per-tenant secret>
 *   ?theme=light|dark — optional parent-site theme pin (first paint; live updates
 *     via digichat:theme postMessage)
 *   ?welcome= / ?placeholder= / ?suggestions= — UI overrides (DataTapStream)
 *
 * Uses stock assistant-ui Thread (ProductStockShell) against POST /api/chat.
 */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { isWebSearchEnabled } from "@/lib/web-search-pref";
import { Key, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ByokCliFlow } from "@/components/byok-cli-flow";
import { ContactMailto } from "@digithings/web";
import { ProductStockShell } from "@/components/stock/product-shell";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  catalogToolsFromClient,
  disabledCatalogIds,
  extraOffFromCatalog,
  type EmbedChatPrefs,
  type EmbedChatPrefsApi,
} from "@/components/stock/embed-chat-prefs";
import { EmbedComposerMenu, type ComposerMenuKind } from "@/components/stock/embed-composer-menu";
import { replaceMcpConfig, connectedMcpConfigs, mcpSessionOverlayHeaderValue } from "@/components/stock/embed-mcp-flow";
import { useAui, useAuiEvent } from "@assistant-ui/react";
import { clientConfigFromEmbedTenant } from "@/lib/deploy-config";
import { skinOwnsPageChrome } from "@/lib/thread-skins";
import {
  useBYOKKey,
  type BYOKProvider,
} from "@/hooks/use-byok-key";
import { readEmbedConversationId, useEmbedDigiChat } from "@/hooks/use-embed-digi-chat";
import {
  BYOK_MODEL_REMEDIABLE_CODES,
  parseEmbedChatError,
  shouldSuggestByokOnEmbedError,
} from "@/lib/embed-chat-error";
import {
  emit,
  readTrialUnlocked,
  resolveEmbedHost,
  shouldChargeGateOnSettle,
  useEmbedGate,
  writeTrialUnlocked,
  writeChatAccessToken,
  EMBED_FREE_TURN_LIMIT,
} from "@/lib/embed-gate";
import { p } from "@/lib/base-path";
import {
  decideEmbedSendGate,
  shouldArmGateCharge,
} from "@/lib/embed-send-gate";
import { takePendingForceTool } from "@/lib/pending-chat-headers";

import {
  buildGatedMessage,
  isUnlockedMessage,
  readUnlockToken,
  PARENT_GATE_TIMEOUT_MS,
  resolveGateFallbackCard,
} from "@/lib/embed-trial-messages";
import { EMBED_TRIAL_TURN_LIMIT } from "@/lib/embed-turn-limits";
import { buildEmbedAccentStyle } from "@/lib/embed-accent-style";
import { useEmbedUiParams } from "@/hooks/use-embed-ui-params";
import type { EmbedUiParams } from "@/lib/embed-ui-params";
import { useEmbedSuggestions } from "@/hooks/use-embed-suggestions";
import {
  useEmbedTenantConfig,
  type EmbedTenantClientConfig,
} from "@/hooks/use-embed-tenant-config";
import { resolveAttributionPlacement, resolveEmbedUiFlags, shouldRenderEmbedBrandHeader } from "@/lib/embed-ui-flags";
import { DEFAULT_LANGUAGE_CODE, tryResolveLanguageInput } from "@/lib/languages";
import { applyEmbedSeed } from "@/lib/embed-seed-apply";
import {
  READY_MESSAGE,
  isAllowedSeedParentOrigin,
  parseSeedMessage,
  resolveReadyTargetOrigin,
} from "@/lib/embed-seed-messages";
import {
  formatParentErrorLine,
  parseParentErrorMessage,
} from "@/lib/embed-parent-error-messages";
import {
  applyEmbedDocumentTheme,
  parseEmbedThemeParam,
  parseThemeMessage,
  type EmbedTheme,
} from "@/lib/embed-theme-messages";
import {
  pageContextCreateAttachment,
  parsePageContextMessage,
  type PageContextMessage,
} from "@/lib/embed-page-context-messages";

type Accent = "digithings" | "digiquant" | "digichat";

const ACCENTS: readonly Accent[] = ["digithings", "digiquant", "digichat"];

const ACCENT_CSS = `
.accent-digithings { --accent: #7c3aed; --accent-foreground: #f5f3ff; }
.accent-digiquant  { --accent: #10b981; --accent-foreground: #ecfdf5; }
.accent-digichat   { --accent: var(--accent-digichat, #e2708a); --accent-foreground: var(--on-accent, #04201c); }
`;

const DEFAULT_WELCOME =
  "Ask a question at the bottom of the page to get started.\n\nAsk anything — the first few turns are free.";

function resolveAccent(raw: string | null | undefined): Accent {
  if (raw && (ACCENTS as readonly string[]).includes(raw)) return raw as Accent;
  return "digichat";
}

/**
 * useSearchParams() (not the searchParams page prop) is required inside this
 * "use client" tree — the prop never delivered ?token=/?host= in production
 * (#1379), silently breaking per-tenant embeds. Suspense is mandatory.
 *
 * `initialTenantCfg` is the one exception, and it does not reopen #1379: it is
 * read from the params by the *server* component in page.tsx, where the prop
 * does work, and arrives here already resolved. The client still re-reads the
 * params itself for everything else.
 */
export default function EmbedClient({
  initialTenantCfg,
}: {
  initialTenantCfg: EmbedTenantClientConfig;
}) {
  return (
    <Suspense fallback={null}>
      <EmbedPageInner initialTenantCfg={initialTenantCfg} />
    </Suspense>
  );
}

function EmbedPageInner({ initialTenantCfg }: { initialTenantCfg: EmbedTenantClientConfig }) {
  const searchParams = useSearchParams();
  const accent = resolveAccent(searchParams.get("accent"));
  const token = searchParams.get("token") ?? undefined;
  const host = searchParams.get("host") ?? undefined;
  const tenantCfg = useEmbedTenantConfig(token, host, initialTenantCfg);
  const urlTheme = parseEmbedThemeParam(searchParams.get("theme"));
  const [parentTheme, setParentTheme] = useState<EmbedTheme | null>(null);
  // Parent postMessage > ?theme= URL pin > tenant registry (default dark).
  const effectiveTheme: EmbedTheme =
    parentTheme ?? urlTheme ?? (tenantCfg.theme === "light" ? "light" : "dark");

  // Plan proof (#3662): the dashboard parent sends a Supabase access_token via
  // postMessage; we exchange it at /api/plan-proof (server verifies claims) and
  // include the HMAC proof in X-Embed-Plan-Proof on every chat request. Raw
  // client-asserted X-Embed-Plan-Tier headers are NEVER trusted by the chat route.
  const [planProof, setPlanProof] = useState<string | null>(null);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onMessage = async (event: MessageEvent) => {
      // Only accept from the configured parent origin.
      if (host) {
        try {
          const parentOrigin = host.includes("://")
            ? new URL(host).origin
            : `https://${host}`;
          if (event.origin !== parentOrigin) return;
        } catch {
          return;
        }
      }
      const data = event.data as {
        type?: string;
        accessToken?: string;
        tier?: string;
      } | null;
      if (!data || data.type !== "digichat:plan-tier") return;
      const accessToken = data.accessToken?.trim();
      if (!accessToken) return;
      // Exchange session token for HMAC-signed proof (claims verified server-side).
      try {
        const embedToken = token ?? searchParams.get("token") ?? undefined;
        const embedHost = host ?? searchParams.get("host") ?? undefined;
        const res = await fetch(p("/api/plan-proof"), {
          method: "POST",
          headers: {
            "content-type": "application/json",
            Authorization: `Bearer ${accessToken}`,
            ...(embedToken ? { "X-Embed-Token": embedToken } : {}),
            ...(embedHost ? { "X-Embed-Host": embedHost } : {}),
          },
          body: "{}",
        });
        if (res.ok) {
          const { proof } = (await res.json()) as { proof?: string };
          if (proof) setPlanProof(proof);
        }
      } catch {
        /* best-effort — chat will 403 without proof, which is correct */
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [host, token, searchParams]);

  useEffect(() => {
    emit("embed_loaded", { accent });
  }, [accent]);

  // Allowed parents for digichat:theme (same allowlist shape as digichat:seed).
  const themeParentOrigins = useMemo(() => {
    const allowed = new Set<string>();
    if (host) {
      try {
        allowed.add(host.includes("://") ? new URL(host).origin : `https://${host}`);
      } catch {
        /* ignore */
      }
    }
    for (const h of ["https://digithings.ai", "https://www.digithings.ai"]) {
      if (isAllowedSeedParentOrigin(h)) allowed.add(h);
    }
    return allowed;
  }, [host]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onMessage = (event: MessageEvent) => {
      const parsed = parseThemeMessage(event, themeParentOrigins);
      if (!parsed) return;
      setParentTheme(parsed.theme);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [themeParentOrigins]);

  // Effective theme drives canon [data-theme] on <html> — the semantic tokens
  // are scoped :root[data-theme="…"] (tokens.css), so a subtree class alone no
  // longer flips the palette. First paint comes from page.tsx (?theme= or
  // tenant); live parent toggles arrive via digichat:theme without reload.
  // ThemeClassSync mirrors [data-theme] onto .dark/.light; the wrapper below
  // keeps its class for Tailwind `dark:` inside the subtree.
  //
  // The app-wide ThemeProvider installs a prefers-color-scheme listener that
  // rewrites <html data-theme> whenever there is no `dt-theme` key — always
  // true for an anonymous embed visitor. Re-assert the effective theme via a
  // MutationObserver so OS flips (and ThemeProvider) cannot silently override
  // a parent- or tenant-forced theme (#1434).
  useEffect(() => {
    const el = document.documentElement;
    const desired = effectiveTheme;
    const apply = () => {
      if (el.getAttribute("data-theme") !== desired) {
        applyEmbedDocumentTheme(desired);
      }
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [effectiveTheme]);

  // The embedding site can theme the widget to its own brand by passing
  // `?accent=#rrggbb` (+ optional `?accentForeground=`), the same override
  // channel it already uses for welcome/placeholder. A validated URL color
  // wins over the tenant-registry accent; both are inline `--accent` so they
  // override the preset `.accent-*` class either way.
  //
  // Read via useEmbedUiParams (post-mount), not useMemo+window — the latter
  // left style=null after SSR/hydration while location.search still had the hex
  // (DataTap terracotta #b5562b regression).
  const urlColors = useEmbedUiParams();
  const accentStyle = buildEmbedAccentStyle(
    urlColors.accent ?? tenantCfg.accent?.color,
    urlColors.accentForeground ?? tenantCfg.accent?.foreground,
  );
  // When a brand hex is active, drop the named `.accent-*` class so the inline
  // style is the sole --accent source (DataTap terracotta regression).
  const brandAccentActive = accentStyle != null;

  // ?wide=1 also means "the embedder wants to show its own page background
  // through" (digithings.ai /chat, /chat/occ — see ChatEmbedShell). The shell
  // (embed/layout.tsx) and body both paint an opaque bg-background by design,
  // for the common case of embedding on an arbitrary host page; there's no
  // prop path from this client tree up to that server-rendered ancestor, so
  // flag it via a DOM attribute + `:has()` in globals.css (same pattern as the
  // [data-theme] sync above, just targeting an ancestor instead of <html>).
  useEffect(() => {
    document.querySelector(".dc-embed-shell")?.setAttribute("data-wide", urlColors.wide ? "1" : "0");
  }, [urlColors.wide]);

  return (
    <>
      <style>{ACCENT_CSS}</style>
      {urlColors.wide ? null : <div className="dc-grain" aria-hidden />}
      <div
        className={`${effectiveTheme === "light" ? "light" : "dark"} ${brandAccentActive ? "" : `accent-${accent}`} relative z-10 flex min-h-0 flex-1 flex-col ${urlColors.wide ? "" : "bg-background"} text-foreground`}
        style={accentStyle}
      >
        <EmbedChat
          accent={accent}
          tenantCfg={tenantCfg}
          token={token}
          host={host}
          uiParams={urlColors}
          planProof={planProof}
        />
      </div>
    </>
  );
}

function EmbedChat({
  accent,
  tenantCfg,
  token,
  host,
  uiParams,
  planProof,
}: {
  accent: Accent;
  tenantCfg: EmbedTenantClientConfig;
  token?: string;
  host?: string;
  uiParams: EmbedUiParams;
  planProof?: string | null;
}) {
  const {
    key: byokKey,
    provider: byokProvider,
    model: byokModel,
    isSet: byokIsSet,
    setKey: setByokKey,
    clearKey: clearByokKey,
  } = useBYOKKey();
  const ungated = tenantCfg.gateMode === "ungated";
  const isTrialForm = tenantCfg.gateMode === "trial_form";
  const llmAccess = tenantCfg.llmAccess;
  const uiFlags = resolveEmbedUiFlags(tenantCfg);
  const stockClient = useMemo(
    () => clientConfigFromEmbedTenant(tenantCfg),
    [tenantCfg],
  );
  const [chatPrefs, setChatPrefs] = useState<EmbedChatPrefs>(() => ({
    ...DEFAULT_EMBED_CHAT_PREFS,
    extra: extraOffFromCatalog(catalogToolsFromClient(stockClient)),
  }));
  const [composerMenu, setComposerMenu] = useState<null | ComposerMenuKind>(null);
  const [providerSeed, setProviderSeed] = useState<string | undefined>();
  const [mcpSeed, setMcpSeed] = useState<string | undefined>();
  // useEmbedDigiChat's transport is frozen on first render (#1339) — a
  // `language` value passed by plain value would stay stuck at mount, so `/lang`
  // would never reach the outgoing header (#2103 / #3418). Mutate the ref in
  // the render body (the "useLatest" idiom). Session-only: English + tools ON
  // on every reload (#3733).
  const chatPrefsRef = useRef(chatPrefs);
  // eslint-disable-next-line react-hooks/refs -- see comment above
  chatPrefsRef.current = chatPrefs;
  const getResponseLanguage = useCallback(() => chatPrefsRef.current.language, []);
  const getSelectedModel = useCallback(() => {
    const id = chatPrefsRef.current.model.trim();
    return id || undefined;
  }, []);
  const planProofRef = useRef(planProof);
  // eslint-disable-next-line react-hooks/refs -- send-time HMAC proof (#1339)
  planProofRef.current = planProof ?? null;
  const getPlanProof = useCallback(() => planProofRef.current, []);

  const webSearchScope = tenantCfg.slug || host?.trim() || "embed";
  const tenantAllowsWeb = uiFlags.webSearch;
  const getEnableWebSearch = useCallback(
    () =>
      isWebSearchEnabled({
        tenantAllows: tenantAllowsWeb,
        userPref: chatPrefsRef.current.webSearch,
      }),
    [tenantAllowsWeb],
  );
  const getDisabledTools = useCallback(
    () => disabledCatalogIds(chatPrefsRef.current).join(","),
    [],
  );
  const getEffort = useCallback(() => chatPrefsRef.current.effort, []);
  const getMcpSession = useCallback(
    () =>
      mcpSessionOverlayHeaderValue(
        connectedMcpConfigs(stockClient.mcp.servers, chatPrefsRef.current.mcpCustom),
        (id) => chatPrefsRef.current.extra[id] !== false,
        stockClient.mcp.allowUserServers === true,
      ),
    [stockClient.mcp.servers, stockClient.mcp.allowUserServers],
  );
  // trial_form still hides BYOK until parent unlock — product rule for DataTap only
  // backend_only never shows BYOK even if misconfigured showByok
  const showByok =
    isTrialForm || llmAccess === "backend_only" ? false : uiFlags.showByok;

  // Mirrors useEmbedGate's own host resolution (resolveEmbedHost(host)) so the
  // persisted trial-unlock flag is keyed identically to the persisted turn
  // counter. Computed here rather than read off `gate.host` after the fact,
  // because `gate` below needs `trialUnlocked` as an input — using `gate.host`
  // would make the two hooks circularly dependent.
  const resolvedHost = useMemo(() => resolveEmbedHost(host), [host]);

  // trialUnlocked persists across reloads (localStorage, keyed by host) —
  // mirrors how embed-gate.ts persists the turn counter (see readTrialUnlocked/
  // writeTrialUnlocked). `host` can change when the iframe URL updates, so this
  // can't be a one-shot lazy useState initializer: it must react to
  // resolvedHost changing, exactly like useEmbedGate's own turnsFor pattern
  // below. Adjusting state DURING RENDER (rather than in a useEffect) means
  // the corrected value is already in place before the gated-postMessage
  // effect ever runs — an effect-based fix would still let one wrong
  // postMessage go out on the initial mount's effect flush, using the stale
  // (false) value.
  const [trialUnlockedFor, setTrialUnlockedFor] = useState<{ host: string; unlocked: boolean }>(
    () => ({ host: resolvedHost, unlocked: readTrialUnlocked(resolvedHost) }),
  );
  if (trialUnlockedFor.host !== resolvedHost) {
    setTrialUnlockedFor({ host: resolvedHost, unlocked: readTrialUnlocked(resolvedHost) });
  }
  const trialUnlocked = trialUnlockedFor.unlocked;
  const unlockTrial = useCallback(() => {
    setTrialUnlockedFor((prev) => {
      writeTrialUnlocked(prev.host, true);
      return { host: prev.host, unlocked: true };
    });
  }, []);

  const [serverGated, setServerGated] = useState(false);
  /** After BYOK save following a free-quota error, regenerate with X-BYOK-* headers. */
  const pendingByokRetryRef = useRef(false);
  /** Panel opened for a model-remediable refusal while a key is already bound — no retry until save. */
  const pendingByokRemediateRef = useRef(false);
  /** Dedupes quota→BYOK open for the same AI SDK error instance/message. */
  const handledQuotaErrorRef = useRef<string | null>(null);

  const gate = useEmbedGate(
    byokIsSet || ungated || trialUnlocked,
    host,
    trialUnlocked ? EMBED_TRIAL_TURN_LIMIT : undefined, // undefined => EMBED_FREE_TURN_LIMIT default
  );

  // trial_form is locked when EITHER the client counter hit the free limit
  // (normal path) OR the server reported a gate (localStorage-bypass path).
  /**
   * The form is raised when the visitor ASKS for it, not the moment the free
   * turns run out.
   *
   * Gating on `gate.locked` put the form up as soon as the third answer
   * finished streaming — on top of the answer, which the visitor had not read
   * yet. (The `!chat.busy` guard on the post below was an earlier attempt at
   * the same problem; it only delayed the cover to the last token.) The
   * natural moment to ask is the FOURTH question: that submission is the
   * visitor telling us they want more, so it is held, the form goes up, and
   * the held question is sent once they are through.
   *
   * `requested` is also what the notice's own button sets, which is the only
   * way back after dismissing the overlay. `nonce` exists because the repost
   * effect dedupes on payload: re-opening produces a byte-identical gated
   * message, so without a changing input the parent would never be told
   * again — the exact dead end where the visitor is left with a notice, a
   * Retry button, and no form.
   */
  const [gateRequest, setGateRequest] = useState({ requested: false, nonce: 0 });
  /** The question that arrived after the free turns were spent, and the one
   *  already released — refs, so neither triggers a render of its own. */
  const heldQuestionRef = useRef<string | null>(null);
  /** Force-tool for a held question (`/search` / `/docs`) — same lifetime as heldQuestionRef. */
  const heldForceToolRef = useRef<string | undefined>(undefined);
  const sentHeldRef = useRef<string | null>(null);
  /**
   * Set (never incremented directly) by every gated send below, then charged
   * by the settle effect near `chat` once the turn actually finishes. chat.send
   * is fire-and-forget — useChat's sendMessage has no success/failure return —
   * so a synchronous gate.increment() right after calling it charges the
   * visitor's free-tier quota regardless of outcome. Verified live: three
   * consecutive failed sends (backend down) fully exhausted the 3-turn quota
   * with zero real answers delivered, permanently gating a visitor who got no
   * value at all. See the settle effect for why chat.rawError is the correct
   * signal to gate the charge on.
   */
  const pendingGateChargeRef = useRef(false);
  /** Visible-page context from popup widget (`digichat:page-context`); consumed once. */
  const pageContextRef = useRef<PageContextMessage | null>(null);
  const [pageContextAttached, setPageContextAttached] = useState(false);
  const consumePageContext = useCallback((): PageContextMessage | null => {
    const ctx = pageContextRef.current;
    if (!ctx) return null;
    pageContextRef.current = null;
    setPageContextAttached(false);
    return ctx;
  }, []);

  const serverGatedOrAsked = serverGated || gateRequest.requested;
  const trialLocked = isTrialForm && !trialUnlocked && serverGatedOrAsked;

  // Standalone (top-level, not embedded) => no parent will show a form. Fall back
  // to the lockedContact card so a visitor is never dead-ended (design spec).
  const isStandalone =
    typeof window !== "undefined" && window.parent === window.self;

  // A legacy iframe embed that omits `?host=` has no channel back to a parent
  // either: the gated postMessage effect below is guarded on `host` and skips
  // itself, and isUnlockedMessage(event, undefined) can never match, so no
  // unlock could ever be honored. Treat that exactly like standalone — fall
  // back to the lockedContact card rather than dead-ending on a form that will
  // never appear.
  const noParentChannel = isStandalone || !host;

  // Stable identity — use-embed-digi-chat.ts's [error, onGated] effect would
  // otherwise re-fire every render off a freshly-allocated arrow function.
  const onGated = useCallback(() => {
    setServerGated(true);
  }, []);

  const chat = useEmbedDigiChat({
    accent,
    token,
    host,
    embedHost: gate.host,
    byokKey: byokIsSet ? byokKey : undefined,
    byokProvider,
    byokModel,
    trialUnlocked,
    onGated: isTrialForm ? onGated : undefined,
    getResponseLanguage,
    getEnableWebSearch,
    getDisabledTools,
    getSelectedModel,
    getMcpSession,
    getEffort,
    getPlanProof,
    // Foundry is append-only until #3475 — never expose truncate-and-resend chrome.
    // Digigraph and Foundry both support turn mutation via X-Digi-Turn-Mode (#3475).
    // Missing backendType (gated default) must not enable regen/edit.
    allowClientTurnMutation:
      tenantCfg.backendType === "digigraph" || tenantCfg.backendType === "foundry",
    features: stockClient.features,
  });

  // Charge the free-tier gate only once a gated send actually settles
  // successfully — never at send time. useChat's setStatus({status:
  // "submitted", error: void 0}) clears the previous error synchronously
  // before this turn's request goes out, so by the time chat.busy flips back
  // to false, chat.rawError reflects only THIS turn's outcome, not a stale
  // one. A failed turn (chat.rawError set) drops the pending charge instead
  // of billing it — a visitor who got no answer keeps their free turn.
  useEffect(() => {
    if (chat.busy || !pendingGateChargeRef.current) return;
    pendingGateChargeRef.current = false;
    if (shouldChargeGateOnSettle(Boolean(chat.rawError))) gate.increment();
  }, [chat.busy, chat.rawError, gate]);

  // Free-tier / rate-limit / model-remediable → stop turn + open in-chat BYOK.
  useEffect(() => {
    if (!chat.rawError) return;
    const errKey = chat.rawError.message;
    if (handledQuotaErrorRef.current === errKey) return;
    const parsed = parseEmbedChatError(chat.rawError);
    if (
      !shouldSuggestByokOnEmbedError({
        llmAccess,
        showByok,
        gateMode: tenantCfg.gateMode,
        errorCode: parsed?.code,
      })
    ) {
      return;
    }
    const remediateWhileBound =
      byokIsSet &&
      !!parsed?.code &&
      BYOK_MODEL_REMEDIABLE_CODES.has(parsed.code);
    if (byokIsSet && !remediateWhileBound) return;
    handledQuotaErrorRef.current = errKey;
    void chat.stop?.();
    if (remediateWhileBound) {
      pendingByokRemediateRef.current = true;
    } else {
      pendingByokRetryRef.current = true;
    }
    // Defer setState out of the synchronous effect body — react-hooks/set-state-in-effect.
    queueMicrotask(() => {
      setComposerMenu("provider");
    });
  }, [chat.rawError, byokIsSet, llmAccess, showByok, tenantCfg.gateMode, chat]);

  // After BYOK save, transport rebuilds with X-BYOK-* — retry the failed turn
  // or release a question held at the gate / byok_only prompt.
  useEffect(() => {
    if (!byokIsSet || chat.busy) return;
    if (pendingByokRemediateRef.current && !pendingByokRetryRef.current) return;
    const held = heldQuestionRef.current;
    if (pendingByokRetryRef.current) {
      pendingByokRetryRef.current = false;
      setComposerMenu(null);
      if (held) {
        heldQuestionRef.current = null;
        const forceTool = heldForceToolRef.current;
        heldForceToolRef.current = undefined;
        void chat.send(held, {
          ...(forceTool ? { forceTool } : {}),
          pageContext: consumePageContext(),
        });
        if (!ungated) pendingGateChargeRef.current = true;
        return;
      }
      chat.onRetry?.();
      return;
    }
    if (held && !gate.locked) {
      heldQuestionRef.current = null;
      const forceTool = heldForceToolRef.current;
      heldForceToolRef.current = undefined;
      void chat.send(held, {
        ...(forceTool ? { forceTool } : {}),
        pageContext: consumePageContext(),
      });
      if (!ungated) pendingGateChargeRef.current = true;
    }
  }, [
    byokIsSet,
    byokKey,
    byokProvider,
    byokModel,
    chat.busy,
    chat.onRetry,
    chat.send,
    ungated,
    gate,
    consumePageContext,
  ]);

  const openByok = useCallback((seed?: string) => {
    setProviderSeed(seed);
    setComposerMenu("provider");
  }, []);

  const onByokSaved = useCallback(
    (key: string, provider: BYOKProvider, model: string) => {
      pendingByokRemediateRef.current = false;
      pendingByokRetryRef.current = true;
      setByokKey(key, provider, model);
      emit("embed_byok_saved", { provider });
      setComposerMenu(null);
      // Retry effect runs once byokIsSet flips (pendingByokRetryRef set above).
    },
    [setByokKey],
  );

  const [seedApplied, setSeedApplied] = useState(false);
  const [hideIntroForSeed, setHideIntroForSeed] = useState(false);
  /** Parent handshake/load failures — stock Thread error transcript lines. */
  const [handshakeError, setHandshakeError] = useState<string | null>(null);

  // Same first-party allowlist as digichat:seed / digichat:theme.
  const firstPartyParentOrigins = useMemo(() => {
    const allowed = new Set<string>();
    if (host) {
      try {
        allowed.add(host.includes("://") ? new URL(host).origin : `https://${host}`);
      } catch {
        /* ignore */
      }
    }
    for (const h of ["https://digithings.ai", "https://www.digithings.ai"]) {
      if (isAllowedSeedParentOrigin(h)) allowed.add(h);
    }
    return allowed;
  }, [host]);

  // Ready handshake targets the *actual* parent browsing context, not virtual
  // ?host= (e.g. occ.digithings.ai). Parent ChatEmbedShell listens on digithings.ai;
  // posting ready to the virtual host is dropped and falsely times out.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.parent === window.self) return;
    const ancestorOrigins =
      "ancestorOrigins" in window.location ? window.location.ancestorOrigins : null;
    const target = resolveReadyTargetOrigin({
      ancestorOrigins,
      referrer: document.referrer,
    });
    if (!target) {
      // Defer setState out of the synchronous effect body — react-hooks/set-state-in-effect.
      queueMicrotask(() => {
        setHandshakeError(formatParentErrorLine("ready_target_missing"));
      });
      return;
    }
    window.parent.postMessage(READY_MESSAGE, target);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onMessage = (event: MessageEvent) => {
      // Late digichat:ready after a ready_timeout still gets theme (and maybe seed)
      // from ChatEmbedShell — clear the sticky terminal line once the parent is
      // talking again on the first-party channel.
      if (parseThemeMessage(event, firstPartyParentOrigins)) {
        setHandshakeError(null);
        return;
      }
      const parentErr = parseParentErrorMessage(event, firstPartyParentOrigins);
      if (!parentErr) return;
      setHandshakeError(formatParentErrorLine(parentErr.code, parentErr.message));
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [firstPartyParentOrigins]);

  useEffect(() => {
    if (typeof window === "undefined" || seedApplied) return;

    const onMessage = (event: MessageEvent) => {
      const parsed = parseSeedMessage(event, firstPartyParentOrigins);
      if (!parsed) return;
      setHandshakeError(null);
      applyEmbedSeed(
        { messages: parsed.messages, pending: parsed.pending },
        { seed: chat.seed, send: chat.send },
      );
      setSeedApplied(true);
      setHideIntroForSeed(true);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [firstPartyParentOrigins, seedApplied, chat.seed, chat.send]);

  // Popup widget (#3421): accept visible-page context from the immediate parent
  // after digichat:ready. Not first-party-only — registered third-party hosts
  // describe their own already-visible DOM (no behind-auth scrape).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const ancestorOrigins =
      "ancestorOrigins" in window.location ? window.location.ancestorOrigins : null;
    const parentOrigin = resolveReadyTargetOrigin({
      ancestorOrigins,
      referrer: document.referrer,
    });
    const onMessage = (event: MessageEvent) => {
      const parsed = parsePageContextMessage(event, parentOrigin);
      if (!parsed) return;
      if (!parsed.text.trim() && !parsed.html?.trim()) return;
      pageContextRef.current = parsed;
      setPageContextAttached(true);
      setHandshakeError(null);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  // The upstream conversation id is the useful handle (it maps to the real backend
  // conversation); fall back to nothing rather than blocking the gate.
  //
  // chat.messages gets a new identity on every streaming chunk, and trialLocked
  // flips true while the gating question's answer is still streaming — so guard on
  // the payload itself, or the parent gets a repost per chunk (and an overlay the
  // visitor dismissed would pop back open). `!chat.busy` additionally holds the
  // post until the 3rd answer has fully streamed in, so the parent's full-bleed
  // overlay doesn't cover the answer from its first token.
  const lastGatedPost = useRef<string | null>(null);
  useEffect(() => {
    if (!trialLocked || isStandalone || !host || chat.busy) return;
    const payload = buildGatedMessage(readEmbedConversationId(gate.host), chat.messages);
    const key = JSON.stringify(payload);
    if (lastGatedPost.current === key) return;
    lastGatedPost.current = key;
    window.parent.postMessage(payload, host);
    // gateRequest.nonce is a dependency, not decoration: re-opening the form
    // after a dismissal produces the same payload, and the ref above would
    // swallow the repost. The re-open handler clears the ref AND bumps the
    // nonce so this effect runs again and the parent actually hears about it.
  }, [trialLocked, isStandalone, host, gate.host, chat.messages, chat.busy, gateRequest.nonce]);

  // Through the form: release the question that was held at the gate, so the
  // visitor gets the answer they asked for rather than having to retype it.
  //
  // The held question is a ref, not state, for two reasons: clearing it would
  // be a synchronous setState inside an effect (which this codebase forbids —
  // see gateTimeoutState above for the same avoidance), and it needs no
  // render of its own. `sentHeld` is what makes the release idempotent, since
  // the effect re-runs on every chat identity change while the answer streams.
  //
  // Call chat.send (not wrappedSend) here: wrappedSend is defined below and
  // would re-capture this effect. Arm the deferred gate charge ourselves so
  // the held fourth question counts the same as any other send (charged only
  // once it settles without error — see the settle effect near `chat`).
  useEffect(() => {
    const question = heldQuestionRef.current;
    if (!trialUnlocked || !question || chat.busy) return;
    if (sentHeldRef.current === question) return;
    sentHeldRef.current = question;
    const forceTool = heldForceToolRef.current;
    heldForceToolRef.current = undefined;
    const hadCtx = pageContextRef.current != null;
    const ctx = consumePageContext();
    void chat.send(question, {
      ...(forceTool ? { forceTool } : {}),
      pageContext: ctx,
    });
    if (!ungated) pendingGateChargeRef.current = true;
    emit("embed_turn_submitted", {
      accent,
      turn: gate.turns + 1,
      byok: byokIsSet,
      page_context: hadCtx,
    });
  }, [trialUnlocked, chat, ungated, gate, accent, byokIsSet, consumePageContext]);

  const reopenTrialForm = useCallback(() => {
    lastGatedPost.current = null;
    setGateRequest((prev) => ({ requested: true, nonce: prev.nonce + 1 }));
  }, []);

  // Fallback for a parent that never answers the gated postMessage (design
  // spec, "Error handling & fallbacks") — see PARENT_GATE_TIMEOUT_MS for the
  // reasoning. "Armed" only when a gated message actually has a parent to
  // reach (trialLocked && !noParentChannel); the standalone/no-host case
  // already renders PaywallCard immediately via noParentChannel, no timer
  // needed. Reset happens during render (same pattern as trialUnlockedFor
  // above) rather than as a synchronous setState in the effect body, per
  // react-hooks/set-state-in-effect. Since trialLocked's own definition
  // (`!trialUnlocked && …`) already flips false the instant trialUnlocked
  // becomes true, `armed` going false also covers the visitor unlocking — so
  // an unlocked visitor can never see the fallback card afterwards.
  const gateTimeoutArmed = trialLocked && !noParentChannel;
  const [gateTimeoutState, setGateTimeoutState] = useState<{
    armed: boolean;
    parentUnresponsive: boolean;
  }>(() => ({ armed: gateTimeoutArmed, parentUnresponsive: false }));
  if (gateTimeoutState.armed !== gateTimeoutArmed) {
    setGateTimeoutState({ armed: gateTimeoutArmed, parentUnresponsive: false });
  }
  const parentUnresponsive = gateTimeoutState.parentUnresponsive;
  useEffect(() => {
    if (!gateTimeoutArmed) return;
    const timer = window.setTimeout(() => {
      setGateTimeoutState((prev) => (prev.armed ? { ...prev, parentUnresponsive: true } : prev));
    }, PARENT_GATE_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [gateTimeoutArmed]);

  useEffect(() => {
    if (!isTrialForm) return;
    const onMessage = (event: MessageEvent) => {
      if (isUnlockedMessage(event, host)) {
        const unlockToken = readUnlockToken(event);
        if (unlockToken && host) {
          writeChatAccessToken(resolveEmbedHost(host), unlockToken);
        }
        unlockTrial();
        setServerGated(false);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [isTrialForm, host, unlockTrial]);

  const welcomeIntro = useMemo(() => {
    if (uiParams.welcome) return uiParams.welcome;
    if (tenantCfg.welcome) return tenantCfg.welcome;
    if (ungated) {
      return "Ask a question at the bottom of the page to get started.\n\nAsk anything about the docs — answers are grounded on the real documentation.";
    }
    return DEFAULT_WELCOME.replace(
      "the first few turns are free",
      `the first ${EMBED_FREE_TURN_LIMIT} are free`,
    );
  }, [uiParams.welcome, tenantCfg.welcome, ungated]);

  const placeholder = uiParams.placeholder ?? tenantCfg.placeholder ?? "ask digichat…";
  const suggestions = useEmbedSuggestions(uiParams.suggestions, tenantCfg);
  const headerTitle = tenantCfg.title;

  const wrappedSend = useCallback(
    (question: string, opts?: { forceTool?: string }) => {
      // byok_only: require a key before any send
      if (llmAccess === "byok_only" && !byokIsSet) {
        heldQuestionRef.current = question;
        heldForceToolRef.current = opts?.forceTool;
        pendingByokRetryRef.current = true;
        setComposerMenu("provider");
        return;
      }
      // Out of free turns: HOLD the question and raise the form. Dropping it
      // on the floor (what this did) meant the visitor's fourth question just
      // vanished — they had typed it, pressed send, and got nothing back.
      if ((gate.locked || trialLocked) && !ungated) {
        heldQuestionRef.current = question;
        heldForceToolRef.current = opts?.forceTool;
        lastGatedPost.current = null;
        setGateRequest((prev) => ({ requested: true, nonce: prev.nonce + 1 }));
        return;
      }
      const hadCtx = pageContextRef.current != null;
      const ctx = consumePageContext();
      void chat.send(question, { ...opts, pageContext: ctx });
      emit("embed_turn_submitted", {
        accent,
        turn: gate.turns + 1,
        byok: byokIsSet,
        page_context: hadCtx,
      });
      if (!ungated) pendingGateChargeRef.current = true;
    },
    [chat, gate, trialLocked, ungated, accent, byokIsSet, llmAccess, consumePageContext],
  );


  // Stock Composer no longer calls wrappedSend — reattach hold/charge via sendGate.
  const sendGate = useMemo(
    () => ({
      shouldHold: (raw: string) => {
        const decision = decideEmbedSendGate({
          locked: gate.locked,
          trialLocked,
          ungated,
          byokRequired: llmAccess === "byok_only" && !byokIsSet,
        });
        return decision.action !== "send";
      },
      onHold: (question: string) => {
        const decision = decideEmbedSendGate({
          locked: gate.locked,
          trialLocked,
          ungated,
          byokRequired: llmAccess === "byok_only" && !byokIsSet,
        });
        heldQuestionRef.current = question;
        // Preserve a catalog force-tool that would have been taken on send.
        heldForceToolRef.current = takePendingForceTool(gate.host);
        if (decision.action === "hold_byok") {
          pendingByokRetryRef.current = true;
          setComposerMenu("provider");
          return;
        }
        lastGatedPost.current = null;
        setGateRequest((prev) => ({ requested: true, nonce: prev.nonce + 1 }));
      },
      onAllowSend: () => {
        if (shouldArmGateCharge(ungated)) {
          pendingGateChargeRef.current = true;
        }
        emit("embed_turn_submitted", {
          accent,
          turn: gate.turns + 1,
          byok: byokIsSet,
          page_context: pageContextRef.current != null,
        });
      },
      takePendingPageContextAttachment: () =>
        pageContextCreateAttachment(pageContextRef.current),
    }),
    [
      gate.locked,
      gate.host,
      gate.turns,
      trialLocked,
      ungated,
      llmAccess,
      byokIsSet,
      accent,
    ],
  );

  const catalog = stockClient.tools.catalog;
  const catalogTools = useMemo(() => catalogToolsFromClient(stockClient), [stockClient]);
  const showModels =
    (stockClient.models.allowPicker === true || stockClient.features.modelPicker === true) &&
    stockClient.models.available.length > 0;
  const prefsApi = useMemo<EmbedChatPrefsApi>(
    () => ({
      prefs: chatPrefs,
      setWebSearch: (value) => setChatPrefs((p) => ({ ...p, webSearch: value })),
      setDigisearch: (value) => setChatPrefs((p) => ({ ...p, digisearch: value })),
      setVault: (value) => setChatPrefs((p) => ({ ...p, vault: value })),
      setExtraTool: (id, value) =>
        setChatPrefs((p) => ({ ...p, extra: { ...p.extra, [id]: value } })),
      extraToolOn: (id) => chatPrefs.extra[id] !== false,
      setMcpConfig: (config, previousId) =>
        setChatPrefs((p) => ({
          ...p,
          mcpCustom: replaceMcpConfig(p.mcpCustom, previousId ?? config.id, config),
        })),
      removeMcpConfig: (id) =>
        setChatPrefs((p) => ({
          ...p,
          mcpCustom: p.mcpCustom.filter((s) => s.id !== id),
        })),
      setLanguage: (code) => {
        const resolved = tryResolveLanguageInput(code) ?? DEFAULT_LANGUAGE_CODE;
        setChatPrefs((p) => ({ ...p, language: resolved }));
      },
      setThinking: (value) => setChatPrefs((p) => ({ ...p, thinking: value })),
      setModel: (id) => setChatPrefs((p) => ({ ...p, model: id })),
      setEffort: (effort) => setChatPrefs((p) => ({ ...p, effort: effort })),
      reset: () =>
        setChatPrefs({
          ...DEFAULT_EMBED_CHAT_PREFS,
          language: DEFAULT_LANGUAGE_CODE,
          extra: extraOffFromCatalog(catalogTools),
        }),
      tenantAllowsWeb,
      showByok,
      showModels,
      hasDigisearch: catalog.some((e) => e.id === "digisearch"),
      hasVault: catalog.some((e) => e.id === "digivault"),
      hasSessions: false,
      allowUserMcp: stockClient.mcp.allowUserServers === true,
      allowAddMcp: stockClient.mcp.allowAddForm === true,
      catalogTools,
      mcpServers: stockClient.mcp.servers,
      sessionKey: gate.host,
      openSettings: () => {
        setComposerMenu("settings");
      },
      openTools: () => {
        setComposerMenu("tools");
      },
      openMcp: (seed?: string) => {
        setMcpSeed(seed);
        setComposerMenu("mcp");
      },
      openByok: (seed?: string) => {
        setProviderSeed(seed);
        setComposerMenu("provider");
      },
      openModels: () => {
        setComposerMenu("models");
      },
      openEffort: () => {
        setComposerMenu("effort");
      },
      openLanguage: () => {
        setComposerMenu("language");
      },
      openSessions: () => {},
      newThread: () => {
        setChatPrefs({
          ...DEFAULT_EMBED_CHAT_PREFS,
          language: DEFAULT_LANGUAGE_CODE,
          extra: extraOffFromCatalog(catalogTools),
        });
        chat.reset?.();
      },
      compactThread: () => {
        setChatPrefs({
          ...DEFAULT_EMBED_CHAT_PREFS,
          language: DEFAULT_LANGUAGE_CODE,
          extra: extraOffFromCatalog(catalogTools),
        });
        chat.reset?.();
      },
      undo: () => {},
      redo: () => {
        chat.regenerate?.();
      },
    }),
    [
      chatPrefs,
      tenantAllowsWeb,
      showByok,
      showModels,
      catalog,
      catalogTools,
      gate.host,
      chat.reset,
      chat.regenerate,
      stockClient.mcp.allowUserServers,
      stockClient.mcp.allowAddForm,
      stockClient.mcp.servers,
    ],
  );


  /* At most one credit, and the footer wins — see resolveAttributionPlacement. */
  const attributionAt = resolveAttributionPlacement({
    attribution: tenantCfg.attribution,
    headerTitle,
  });
  const footerAttribution = attributionAt === "footer";
  const headerAttribution = attributionAt === "header";

  // Language is `/language` on the composer (#3418 / #3733). First-party
  // digichat skin uses launcher chrome — skip the in-iframe title row.
  const headerSlot = shouldRenderEmbedBrandHeader({
    skin: stockClient.chrome.skin,
    headerTitle,
  }) ? (
    <header className="dc-brand">
      <span>{headerTitle}</span>
      {headerAttribution ? (
        <span className="dc-brand-by">
          (
          <a
            href="https://digithings.ai"
            target="_blank"
            rel="noreferrer noopener"
            className="dc-brand-link"
          >
            by digichat
          </a>
          )
        </span>
      ) : null}
    </header>
  ) : null;

  const footerSlot = footerAttribution ? (
    <p className="dc-attribution">
      powered by digichat — a{" "}
      <a href="https://digithings.ai" target="_blank" rel="noreferrer noopener">
        digithings
      </a>{" "}
      product.
    </p>
  ) : null;

  // turn_limited: only raise paywall when the visitor asks past the free
  // limit (gateRequest.requested). Showing it on gate.locked alone replaced
  // the Thread after the third answer — so they could never type the fourth
  // question that the hold path was meant to capture.
  const gateForm =
    trialLocked ? (
      resolveGateFallbackCard({ noParentChannel, parentUnresponsive }) === "paywall" ? (
        <PaywallCard
          lockedContact={tenantCfg.lockedContact}
          onSave={onByokSaved}
          initialProvider={byokProvider}
          initialModel={byokModel}
        />
      ) : (
        <TrialGatePlaceholder onOpen={reopenTrialForm} />
      )
    ) : gate.locked && !ungated && !isTrialForm && gateRequest.requested ? (
      <PaywallCard
        lockedContact={tenantCfg.lockedContact}
        onSave={onByokSaved}
        initialProvider={byokProvider}
        initialModel={byokModel}
      />
    ) : null;

  if (gateForm) {
    return (
      <div className="flex h-dvh flex-col" data-chrome-mode="embed" data-thread-skin={stockClient.chrome.skin}>
        {headerSlot}
        <div className="flex flex-1 items-center justify-center p-4">{gateForm}</div>
        {footerSlot}
      </div>
    );
  }

  // Composer chip reads the last parent snapshot at render; send consumes the same ref.
  // eslint-disable-next-line react-hooks/refs -- useLatest page-context for the attachment chip
  const pageContextSnapshot = pageContextAttached ? pageContextRef.current : null;
  const pageContextAttachment = pageContextCreateAttachment(pageContextSnapshot);
  const pageContextTs = pageContextSnapshot?.ts ?? null;

  return (
    <EmbedChatPrefsProvider value={prefsApi}>
      <ProductStockShell
        runtime={chat.runtime}
        clientConfig={stockClient}
        persistence="none"
        sendGate={sendGate}
        sessionKey={gate.host}
        webSearchScope={webSearchScope}
        onWebSearchChange={(on) => {
          setChatPrefs((p) => ({ ...p, webSearch: on }));
        }}
        welcome={hideIntroForSeed ? undefined : welcomeIntro || undefined}
        suggestions={suggestions}
        placeholder={placeholder}
        className={uiParams.wide ? "min-h-dvh" : "h-dvh"}
        headerSlot={
          skinOwnsPageChrome(stockClient.chrome.skin) ? null : headerSlot
        }
        footerSlot={
          <>
            <PageContextComposerBridge
              attachment={pageContextAttachment}
              contextTs={pageContextTs}
              onComposerSend={consumePageContext}
            />
            {handshakeError ? (
              <div
                role="alert"
                className="border-t border-border/40 px-3 py-2 text-sm"
                style={{ color: "var(--danger, var(--destructive))" }}
              >
                {handshakeError}
              </div>
            ) : null}
            {footerSlot}
          </>
        }
      />
      {composerMenu ? (
        <EmbedComposerMenu
          kind={composerMenu}
          models={stockClient.models.available}
          onClose={() => {
            setComposerMenu(null);
            setProviderSeed(undefined);
            setMcpSeed(undefined);
          }}
          onActivateProvider={showByok ? onByokSaved : undefined}
          onClearProvider={showByok ? clearByokKey : undefined}
          providerActive={byokIsSet ? { provider: byokProvider, model: byokModel } : null}
          initialProvider={byokIsSet ? byokProvider : undefined}
          providerSeed={providerSeed}
          mcpSeed={mcpSeed}
        />
      ) : null}
    </EmbedChatPrefsProvider>
  );
}

function PageContextComposerBridge({
  attachment,
  contextTs,
  onComposerSend,
}: {
  attachment: ReturnType<typeof pageContextCreateAttachment>;
  contextTs: number | null;
  onComposerSend: () => void;
}) {
  const aui = useAui();
  const addedTsRef = useRef<number | null>(null);
  const consumedTsRef = useRef<number | null>(null);
  useAuiEvent("composer.send", () => {
    if (contextTs != null) consumedTsRef.current = contextTs;
    onComposerSend();
  });
  useEffect(() => {
    if (!attachment || contextTs == null) return;
    if (consumedTsRef.current === contextTs) return;
    if (addedTsRef.current === contextTs) return;
    addedTsRef.current = contextTs;
    void aui.composer.addAttachment(attachment);
  }, [attachment, contextTs, aui]);
  return null;
}

function PaywallCard({
  lockedContact,
  onSave,
  initialProvider,
  initialModel,
}: {
  lockedContact?: string;
  onSave: (key: string, provider: BYOKProvider, model: string) => void;
  initialProvider?: BYOKProvider;
  initialModel?: string;
}) {
  const [showBYOK, setShowBYOK] = useState(false);

  useEffect(() => {
    emit("embed_gate_hit", {});
  }, []);

  // Contact-us variant: tenants that would rather route capped visitors to
  // sales than offer BYOK set `lockedContact` (see embed-tenants.ts). Placed
  // after all hooks so hook order stays stable (rules-of-hooks).
  if (lockedContact) {
    return (
      <div className="border-t border-border bg-muted/40 p-4">
        <p className="mb-2 text-sm font-medium">
          You&rsquo;ve used your {EMBED_FREE_TURN_LIMIT} free questions.
        </p>
        <p className="text-xs text-muted-foreground">
          For more, get in touch at{" "}
          <ContactMailto
            email={lockedContact}
            showAddress
            className="font-medium underline"
            style={{ color: "var(--accent)" }}
          >
            our contact address
          </ContactMailto>
          .
        </p>
      </div>
    );
  }

  if (showBYOK) {
    return (
      <ByokCliFlow
        onActivate={(key, provider, model) => {
          onSave(key, provider, model);
          setShowBYOK(false);
        }}
        onClose={() => setShowBYOK(false)}
        initialProvider={initialProvider}
        initialModel={initialModel}
        title={`byok — ${EMBED_FREE_TURN_LIMIT} free questions used`}
      />
    );
  }

  return (
    <div className="border-t border-border bg-muted/40 p-4">
      <p className="mb-2 text-sm font-medium">
        You&rsquo;ve used your {EMBED_FREE_TURN_LIMIT} free questions.
      </p>
      <p className="mb-3 text-xs text-muted-foreground">
        Bring your own OpenRouter, OpenAI, Anthropic, or Gemini key for unlimited chat — the key
        stays in session memory only (refresh clears it). After a chat starts, type{" "}
        <code className="font-mono">/provider</code> anytime. Or open the full digichat app.
      </p>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => setShowBYOK(true)}
        >
          <Key className="mr-1.5 size-3.5" />
          Bring your own key (/provider)
        </Button>
        <a
          href="https://digithings.ai/chat"
          target="_blank"
          rel="noreferrer noopener"
          onClick={() => emit("embed_open_full_chat", {})}
          className="inline-flex items-center rounded-none border border-border bg-transparent px-3 py-1.5 text-sm font-medium hover:bg-muted"
        >
          <ExternalLink className="mr-1.5 size-3.5" />
          Open digichat
        </a>
      </div>
    </div>
  );
}

function TrialGatePlaceholder({ onOpen }: { onOpen: () => void }) {
  return (
    <div className="border-t border-border bg-muted/40 p-4">
      <p className="text-sm font-medium">
        You&rsquo;ve used your {EMBED_FREE_TURN_LIMIT} free questions. Complete{" "}
        <button
          type="button"
          onClick={onOpen}
          className="underline underline-offset-2 hover:opacity-80"
        >
          the trial form
        </button>{" "}
        to keep chatting.
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        Closed the form by mistake?{" "}
        <button
          type="button"
          onClick={onOpen}
          className="font-medium underline underline-offset-2 hover:opacity-80"
          style={{ color: "var(--accent)" }}
        >
          Retry
        </button>
      </p>
    </div>
  );
}
