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
 * Uses assistant-ui primitives (`CliThread`) with the shared CLI session skin.
 */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  isWebSearchEnabled,
  readWebSearchPref,
  writeWebSearchPref,
} from "@/lib/web-search-pref";
import { parseSlashInput } from "@digithings/digichat-ui";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { CliThread } from "@/components/assistant-ui/cli-thread";
import { Key, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ByokCliFlow } from "@/components/byok-cli-flow";
import { ContactMailto } from "@/components/ContactMailto";
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
import { resolveAttributionPlacement, resolveEmbedUiFlags } from "@/lib/embed-ui-flags";
import { detectBrowserLanguageCode } from "@/lib/languages";
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
  formatPageContextForPrompt,
  parsePageContextMessage,
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
}: {
  accent: Accent;
  tenantCfg: EmbedTenantClientConfig;
  token?: string;
  host?: string;
  uiParams: EmbedUiParams;
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
  const [language, setLanguage] = useState(() => detectBrowserLanguageCode());
  // useEmbedDigiChat's transport is frozen on first render (#1339) — a
  // `language` value passed by plain value would stay stuck at whatever
  // detectBrowserLanguageCode() returned at mount, so `/lang` would never
  // reach the outgoing header (#2103 / #3418). Mutate the ref directly in
  // the render body (the "useLatest" idiom) rather than in a useEffect — an
  // effect would lag one render behind and could race a fast pick-then-send. The value is
  // deliberately NOT persisted anywhere (no localStorage/sessionStorage): the
  // approved design is session-only, resetting to a fresh browser-locale
  // auto-detect on every reload.
  const languageRef = useRef(language);
  // Deliberate "useLatest" escape hatch: mutating .current here (not in an
  // effect) is what makes send-time reads see the value from the render that
  // just committed, with zero lag. useEffectEvent can't replace this — its
  // returned function may only be called from an Effect/Effect Event in the
  // SAME component and may not be passed down, but getResponseLanguage is
  // deliberately passed down into useEmbedDigiChat and invoked later from
  // prepareSendMessagesRequest.
  // eslint-disable-next-line react-hooks/refs -- see comment above
  languageRef.current = language;
  const getResponseLanguage = useCallback(() => languageRef.current, []);

  // Opt-in web search (#3420) — tenant allow + user localStorage pref; default off.
  // Adjust during render when scope changes (same pattern as trialUnlockedFor).
  const webSearchScope = tenantCfg.slug || host?.trim() || "embed";
  const [webSearchState, setWebSearchState] = useState<{
    scope: string;
    pref: boolean;
  }>(() => ({ scope: webSearchScope, pref: false }));
  if (webSearchState.scope !== webSearchScope) {
    setWebSearchState({
      scope: webSearchScope,
      pref: typeof window !== "undefined" ? readWebSearchPref(webSearchScope) : false,
    });
  }
  // Hydrate from localStorage once on the client (SSR starts false).
  const [webHydrated, setWebHydrated] = useState(false);
  if (typeof window !== "undefined" && !webHydrated) {
    setWebHydrated(true);
    const stored = readWebSearchPref(webSearchScope);
    if (stored !== webSearchState.pref) {
      setWebSearchState({ scope: webSearchScope, pref: stored });
    }
  }
  const webSearchPref = webSearchState.pref;
  const webSearchUserRef = useRef(webSearchPref);
  // eslint-disable-next-line react-hooks/refs -- send-time read via getEnableWebSearch
  webSearchUserRef.current = webSearchPref;
  const tenantAllowsWeb = uiFlags.webSearch;
  const getEnableWebSearch = useCallback(
    () =>
      isWebSearchEnabled({
        tenantAllows: tenantAllowsWeb,
        userPref: webSearchUserRef.current,
      }),
    [tenantAllowsWeb],
  );
  const toggleWebSearch = useCallback(() => {
    setWebSearchState((prev) => {
      const next = !prev.pref;
      writeWebSearchPref(prev.scope, next);
      return { scope: prev.scope, pref: next };
    });
  }, []);

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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [quotaPrompt, setQuotaPrompt] = useState(false);
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
  const pageContextRef = useRef<string | null>(null);
  const [pageContextAttached, setPageContextAttached] = useState(false);
  const consumePageContextPrefix = useCallback((question: string): string => {
    const ctx = pageContextRef.current;
    if (!ctx) return question;
    pageContextRef.current = null;
    setPageContextAttached(false);
    return `${ctx}\n\n---\n\nUser question:\n${question}`;
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
    // Foundry is append-only until #3475 — never expose truncate-and-resend chrome.
    // Digigraph and Foundry both support turn mutation via X-Digi-Turn-Mode (#3475).
    // Missing backendType (gated default) must not enable regen/edit.
    allowClientTurnMutation:
      tenantCfg.backendType === "digigraph" || tenantCfg.backendType === "foundry",
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
      setQuotaPrompt(!remediateWhileBound);
      setSettingsOpen(true);
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
      setQuotaPrompt(false);
      setSettingsOpen(false);
      if (held) {
        heldQuestionRef.current = null;
        const forceTool = heldForceToolRef.current;
        heldForceToolRef.current = undefined;
        void chat.send(consumePageContextPrefix(held), forceTool ? { forceTool } : undefined);
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
      void chat.send(consumePageContextPrefix(held), forceTool ? { forceTool } : undefined);
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
    consumePageContextPrefix,
  ]);

  const openSettings = useCallback(() => {
    setQuotaPrompt(false);
    setSettingsOpen(true);
  }, []);

  const onByokSaved = useCallback(
    (key: string, provider: BYOKProvider, model: string) => {
      pendingByokRemediateRef.current = false;
      pendingByokRetryRef.current = true;
      setByokKey(key, provider, model);
      emit("embed_byok_saved", { provider });
      setSettingsOpen(false);
      // Retry effect runs once byokIsSet flips (pendingByokRetryRef set above).
    },
    [setByokKey],
  );

  const [seedApplied, setSeedApplied] = useState(false);
  const [hideIntroForSeed, setHideIntroForSeed] = useState(false);
  /** Parent handshake/load failures — DigiChatSession `.dtc-error` transcript lines. */
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
      const formatted = formatPageContextForPrompt(parsed);
      if (!formatted) return;
      pageContextRef.current = formatted;
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
    void chat.send(consumePageContextPrefix(question), forceTool ? { forceTool } : undefined);
    if (!ungated) pendingGateChargeRef.current = true;
    emit("embed_turn_submitted", {
      accent,
      turn: gate.turns + 1,
      byok: byokIsSet,
      page_context: hadCtx,
    });
  }, [trialUnlocked, chat, ungated, gate, accent, byokIsSet, consumePageContextPrefix]);

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
    let base: string;
    if (uiParams.welcome) base = uiParams.welcome;
    else if (tenantCfg.welcome) base = tenantCfg.welcome;
    else if (ungated) {
      base =
        "Ask a question at the bottom of the page to get started.\n\nAsk anything about the docs — answers are grounded on the real documentation.";
    } else {
      base = DEFAULT_WELCOME.replace(
        "the first few turns are free",
        `the first ${EMBED_FREE_TURN_LIMIT} are free`,
      );
    }
    if (pageContextAttached) {
      return `${base}\n\nPage context from this host is attached — ask about what you see on the page.`;
    }
    return base;
  }, [uiParams.welcome, tenantCfg.welcome, ungated, pageContextAttached]);

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
        setSettingsOpen(true);
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
      void chat.send(consumePageContextPrefix(question), opts);
      emit("embed_turn_submitted", {
        accent,
        turn: gate.turns + 1,
        byok: byokIsSet,
        page_context: hadCtx,
      });
      if (!ungated) pendingGateChargeRef.current = true;
    },
    [chat, gate, trialLocked, ungated, accent, byokIsSet, llmAccess, consumePageContextPrefix],
  );

  /* At most one credit, and the footer wins — see resolveAttributionPlacement. */
  const attributionAt = resolveAttributionPlacement({
    attribution: tenantCfg.attribution,
    headerTitle,
  });
  const footerAttribution = attributionAt === "footer";
  const headerAttribution = attributionAt === "header";

  // Language is `/lang` on the composer (#3418) — the top-right dropdown is gone.
  const headerSlot = headerTitle ? (
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

  const showByokOnError =
    !handshakeError &&
    !trialLocked &&
    shouldSuggestByokOnEmbedError({
      llmAccess,
      showByok,
      gateMode: tenantCfg.gateMode,
      errorCode: parseEmbedChatError(chat.rawError)?.code,
      errorMessage: chat.error,
    });

  return (
    <AssistantRuntimeProvider runtime={chat.runtime}>
      <CliThread
        placeholder={placeholder}
        suggestions={suggestions}
        layout={uiFlags.layout}
        className={uiParams.wide ? "dc-session--wide" : undefined}
        ariaLabel={headerTitle ?? "digichat embed"}
        emptyHint={
          hideIntroForSeed
            ? null
            : welcomeIntro
              ? (
                  <div className="dc-term-row dc-term-row-assistant">
                    <span className="dc-term-marker">▸</span>
                    <div className="dc-term-body" style={{ color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                      {welcomeIntro}
                    </div>
                  </div>
                )
              : undefined
        }
        headerSlot={headerSlot}
        footerSlot={footerSlot}
        slashVisibility={{ webSearch: tenantAllowsWeb, byok: showByok }}
        onLanguageChange={setLanguage}
        onOpenSettings={showByok ? openSettings : undefined}
        onReset={chat.reset}
        onSendRequest={(text, opts) => {
          wrappedSend(text, opts);
          return true;
        }}
        onSlashCommand={(raw) => {
          const parsed = parseSlashInput(raw);
          if (parsed.kind === "command" && parsed.command.id === "websearch" && tenantAllowsWeb) {
            toggleWebSearch();
            return true;
          }
          return false;
        }}
        settingsPanel={
          showByok && settingsOpen ? (
            <ByokCliFlow
              onClose={() => setSettingsOpen(false)}
              onActivate={onByokSaved}
              onClear={clearByokKey}
              active={
                byokIsSet
                  ? { provider: byokProvider, model: byokModel }
                  : null
              }
              initialProvider={byokProvider}
              initialModel={byokModel}
              title={
                quotaPrompt
                  ? "byok — free tier exhausted"
                  : "byok configure"
              }
            />
          ) : undefined
        }
        formReplacement={
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
          ) : gate.locked && !ungated && !isTrialForm ? (
            <PaywallCard
              lockedContact={tenantCfg.lockedContact}
              onSave={onByokSaved}
              initialProvider={byokProvider}
              initialModel={byokModel}
            />
          ) : undefined
        }
        errorText={handshakeError ?? (trialLocked ? null : chat.error)}
        errorAction={
          showByokOnError && !handshakeError && !trialLocked ? (
            <button type="button" className="dc-inline-link" onClick={openSettings}>
              Add your API key (/byok)
            </button>
          ) : undefined
        }
        disabled={Boolean((gate.locked || trialLocked) && !ungated)}
      />
    </AssistantRuntimeProvider>
  );
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
            className="font-medium underline"
            style={{ color: "var(--accent)" }}
          />
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
        <code className="font-mono">/byok</code> anytime. Or open the full digichat app.
      </p>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => setShowBYOK(true)}
        >
          <Key className="mr-1.5 size-3.5" />
          Bring your own key (/byok)
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
