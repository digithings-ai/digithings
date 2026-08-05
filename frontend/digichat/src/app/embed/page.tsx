"use client";

/**
 * /embed — minimal unauthenticated chat surface for iframe embedding.
 *
 *   ?accent=digithings|digiquant|digichat   (default: digichat)
 *   ?host=<the embedding page's own origin> — see resolveEmbedHost() (#1372)
 *   ?token=<per-tenant secret>
 *   ?welcome= / ?placeholder= / ?suggestions= — UI overrides (DataTapStream)
 *
 * Uses the shared @digithings/digichat-ui DigiChatSession widget.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DigiChatSession } from "@digithings/digichat-ui";
import { Key, ExternalLink, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useBYOKKey,
  validateBYOKKey,
  validateBYOKModel,
  type BYOKProvider,
} from "@/hooks/use-byok-key";
import { readEmbedConversationId, useEmbedDigiChat } from "@/hooks/use-embed-digi-chat";
import {
  emit,
  readTrialUnlocked,
  resolveEmbedHost,
  useEmbedGate,
  writeTrialUnlocked,
  EMBED_FREE_TURN_LIMIT,
} from "@/lib/embed-gate";
import {
  buildGatedMessage,
  isUnlockedMessage,
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

type Accent = "digithings" | "digiquant" | "digichat";

const ACCENTS: readonly Accent[] = ["digithings", "digiquant", "digichat"];

const ACCENT_CSS = `
.accent-digithings { --accent: #7c3aed; --accent-foreground: #f5f3ff; }
.accent-digiquant  { --accent: #10b981; --accent-foreground: #ecfdf5; }
.accent-digichat   { --accent: #1f1f1f; --accent-foreground: #e6e6e6; }
`;

const DEFAULT_WELCOME =
  "Ask a question at the bottom of the page to get started.\n\nAsk anything — the first few turns are free.";

function resolveAccent(raw: string | null | undefined): Accent {
  if (raw && (ACCENTS as readonly string[]).includes(raw)) return raw as Accent;
  return "digichat";
}

type EmbedPageProps = {
  searchParams:
    | Promise<{ accent?: string; token?: string; host?: string }>
    | { accent?: string; token?: string; host?: string };
};

export default function EmbedPage({ searchParams }: EmbedPageProps) {
  const [accent, setAccent] = useState<Accent>("digichat");
  const [token, setToken] = useState<string | undefined>(undefined);
  const [host, setHost] = useState<string | undefined>(undefined);
  const tenantCfg = useEmbedTenantConfig(token, host);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve(searchParams).then((sp) => {
      if (cancelled) return;
      setAccent(resolveAccent(sp?.accent));
      setToken(sp?.token);
      setHost(sp?.host);
    });
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  useEffect(() => {
    emit("embed_loaded", { accent });
  }, [accent]);

  // Tenant theme drives the canon [data-theme] on <html> — the semantic
  // tokens are scoped :root[data-theme="…"] (tokens.css), so a subtree class
  // alone no longer flips the palette. Default stays dark like the pre-canon
  // embed (this page is its own iframe document, so the root flip is scoped
  // to the embed). The .dark/.light classes follow via ThemeClassSync
  // (providers.tsx); the wrapper div below keeps its class for the Tailwind
  // `dark:` variant inside the subtree.
  //
  // The app-wide ThemeProvider (providers.tsx, from @digithings/web) installs a
  // persistent prefers-color-scheme listener that rewrites <html data-theme> to
  // the OS scheme whenever there is no `dt-theme` localStorage key — always the
  // case for an anonymous embed visitor, who never toggles the theme. Without a
  // guard, a mid-session OS light↔dark switch would silently flip a tenant's
  // forced theme. Re-assert the tenant theme via a MutationObserver so it wins
  // over any external writer; the guarded write (only when it actually differs)
  // keeps the observer loop-free.
  useEffect(() => {
    const el = document.documentElement;
    const desired = tenantCfg.theme === "light" ? "light" : "dark";
    const apply = () => {
      if (el.getAttribute("data-theme") !== desired) {
        el.setAttribute("data-theme", desired);
      }
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, [tenantCfg.theme]);

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
  // When a brand hex is active, drop the named `.accent-*` class — ACCENT_CSS
  // paints `.accent-digichat { --accent: #1f1f1f }`, which is exactly the
  // wrong color observers saw when the inline style failed to attach.
  const brandAccentActive = accentStyle != null;

  return (
    <>
      <style>{ACCENT_CSS}</style>
      <div className="dc-grain" aria-hidden />
      <div
        className={`${tenantCfg.theme === "light" ? "light" : "dark"} ${brandAccentActive ? "" : `accent-${accent}`} relative z-10 flex min-h-0 flex-1 flex-col bg-background text-foreground`}
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
  const { key: byokKey, provider: byokProvider, model: byokModel, isSet: byokIsSet } =
    useBYOKKey();
  const ungated = tenantCfg.gateMode === "ungated";
  const isTrialForm = tenantCfg.gateMode === "trial_form";
  const showByok = !ungated && !isTrialForm; // trial_form defers unlock to the parent form, not BYOK

  // Mirrors useEmbedGate's own host resolution (resolveEmbedHost(host)) so the
  // persisted trial-unlock flag is keyed identically to the persisted turn
  // counter. Computed here rather than read off `gate.host` after the fact,
  // because `gate` below needs `trialUnlocked` as an input — using `gate.host`
  // would make the two hooks circularly dependent.
  const resolvedHost = useMemo(() => resolveEmbedHost(host), [host]);

  // trialUnlocked persists across reloads (localStorage, keyed by host) —
  // mirrors how embed-gate.ts persists the turn counter (see readTrialUnlocked/
  // writeTrialUnlocked). `host` arrives asynchronously (resolved from a
  // searchParams Promise in the parent EmbedPage), so this can't be a one-shot
  // lazy useState initializer: it must react to resolvedHost changing, exactly
  // like useEmbedGate's own turnsFor pattern below. Adjusting state DURING
  // RENDER (rather than in a useEffect) means the corrected value is already
  // in place before the gated-postMessage effect ever runs — an effect-based
  // fix would still let one wrong postMessage go out on the initial mount's
  // effect flush, using the stale (false) value.
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

  const gate = useEmbedGate(
    byokIsSet || ungated || trialUnlocked,
    host,
    trialUnlocked ? EMBED_TRIAL_TURN_LIMIT : undefined, // undefined => EMBED_FREE_TURN_LIMIT default
  );

  // trial_form is locked when EITHER the client counter hit the free limit
  // (normal path) OR the server reported a gate (localStorage-bypass path).
  const trialLocked = isTrialForm && !trialUnlocked && (gate.locked || serverGated);

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
  });

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
  }, [trialLocked, isStandalone, host, gate.host, chat.messages, chat.busy]);

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
    (question: string) => {
      if ((gate.locked || trialLocked) && !ungated) return;
      void chat.send(question);
      emit("embed_turn_submitted", {
        accent,
        turn: gate.turns + 1,
        byok: byokIsSet,
      });
      if (!ungated) gate.increment();
    },
    [chat, gate, trialLocked, ungated, accent, byokIsSet],
  );

  const headerSlot =
    headerTitle || !ungated ? (
      <header className="dc-brand">
        {headerTitle ? <span>{headerTitle}</span> : <span>digichat</span>}
        {headerTitle ? (
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
        {!ungated ? (
          <span className="dc-header-meta" aria-label={`Turns used: ${gate.turns} of ${gate.limit}`}>
            {byokIsSet ? "BYOK unlocked" : `${gate.turns}/${gate.limit} free`}
          </span>
        ) : null}
      </header>
    ) : null;

  const footerSlot =
    tenantCfg.attribution && !headerTitle ? (
      <p className="dc-attribution">
        powered by digichat — a{" "}
        <a href="https://digithings.ai" target="_blank" rel="noreferrer noopener">
          digithings
        </a>{" "}
        product.
      </p>
    ) : null;

  return (
    <DigiChatSession
      welcomeIntro={welcomeIntro}
      suggestions={suggestions}
      placeholder={placeholder}
      showByok={showByok}
      showStatusBar={false}
      layout="embed"
      chat={{ ...chat, send: wrappedSend }}
      headerSlot={headerSlot}
      footerSlot={footerSlot}
      formReplacement={
        trialLocked ? (
          resolveGateFallbackCard({ noParentChannel, parentUnresponsive }) === "paywall" ? (
            <PaywallCard lockedContact={tenantCfg.lockedContact} />
          ) : (
            <TrialGatePlaceholder />
          )
        ) : gate.locked && !ungated && !isTrialForm ? (
          <PaywallCard lockedContact={tenantCfg.lockedContact} />
        ) : undefined
      }
      showIntro={!gate.locked && !trialLocked}
      ariaLabel={headerTitle ?? "digichat embed"}
    />
  );
}

function PaywallCard({ lockedContact }: { lockedContact?: string }) {
  const { setKey } = useBYOKKey();
  const [showBYOK, setShowBYOK] = useState(false);
  const [inputKey, setInputKey] = useState("");
  const [provider, setProvider] = useState<BYOKProvider>("openrouter");
  const [inputModel, setInputModel] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    emit("embed_gate_hit", {});
  }, []);

  const onSave = useCallback(() => {
    const err = validateBYOKKey(inputKey, provider) ?? validateBYOKModel(inputModel, provider);
    if (err) {
      setError(err);
      return;
    }
    setKey(inputKey, provider, inputModel.trim());
    emit("embed_byok_saved", { provider });
    setInputKey("");
    setInputModel("");
    setShowBYOK(false);
  }, [inputKey, inputModel, provider, setKey]);

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
          <a
            href={`mailto:${lockedContact}`}
            className="font-medium underline"
            style={{ color: "var(--accent)" }}
          >
            {lockedContact}
          </a>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="border-t border-border bg-muted/40 p-4">
      <p className="mb-2 text-sm font-medium">
        You&rsquo;ve used your {EMBED_FREE_TURN_LIMIT} free questions.
      </p>
      <p className="mb-3 text-xs text-muted-foreground">
        Bring your own OpenRouter, OpenAI, or Anthropic key for unlimited chat — your key is
        stored only in your browser. Or open the full DigiChat app.
      </p>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => setShowBYOK((v) => !v)}
          style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
        >
          <Key className="mr-1.5 size-3.5" />
          Bring your own key
        </Button>
        <a
          href="https://chat.digithings.ai"
          target="_blank"
          rel="noreferrer noopener"
          onClick={() => emit("embed_open_full_chat", {})}
          className="inline-flex items-center rounded-md border border-border bg-transparent px-3 py-1.5 text-sm font-medium hover:bg-muted"
        >
          <ExternalLink className="mr-1.5 size-3.5" />
          Open DigiChat
        </a>
      </div>

      {showBYOK && (
        <div className="mt-4 space-y-3">
          <div className="flex gap-2">
            {(["openrouter", "openai", "anthropic", "gemini"] as BYOKProvider[]).map((p) => (
              <Button
                key={p}
                type="button"
                size="sm"
                variant={provider === p ? "default" : "outline"}
                className="flex-1 capitalize"
                onClick={() => setProvider(p)}
              >
                {p === "openai"
                  ? "OpenAI"
                  : p === "anthropic"
                    ? "Anthropic"
                    : p === "gemini"
                      ? "Gemini"
                      : "OpenRouter"}
              </Button>
            ))}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="embed-byok-key" className="text-xs">
              API key
            </Label>
            <div className="relative flex items-center">
              <Input
                id="embed-byok-key"
                type={showKey ? "text" : "password"}
                value={inputKey}
                onChange={(e) => {
                  setInputKey(e.target.value);
                  setError(null);
                }}
                placeholder={
                  provider === "openai"
                    ? "sk-…"
                    : provider === "anthropic"
                      ? "sk-ant-…"
                      : provider === "gemini"
                        ? "AIza…"
                        : "sk-or-v1-…"
                }
                autoComplete="off"
                spellCheck={false}
                className="pr-9 font-mono text-sm"
                aria-invalid={!!error}
              />
              <button
                type="button"
                className="absolute right-2.5 text-muted-foreground hover:text-foreground"
                onClick={() => setShowKey((v) => !v)}
                aria-label={showKey ? "Hide key" : "Show key"}
                tabIndex={-1}
              >
                {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            {error && <p className="text-[11px] text-destructive">{error}</p>}
          </div>
          {provider === "openrouter" ? (
            <div className="space-y-1.5">
              <Label htmlFor="embed-byok-model" className="text-xs">
                Model
              </Label>
              <Input
                id="embed-byok-model"
                type="text"
                value={inputModel}
                onChange={(e) => {
                  setInputModel(e.target.value);
                  setError(null);
                }}
                placeholder="openai/gpt-4o-mini"
                autoComplete="off"
                spellCheck={false}
                className="font-mono text-sm"
              />
            </div>
          ) : null}
          <Button type="button" size="sm" onClick={onSave} disabled={!inputKey}>
            Save key
          </Button>
        </div>
      )}
    </div>
  );
}

function TrialGatePlaceholder() {
  return (
    <div className="border-t border-border bg-muted/40 p-4">
      <p className="text-sm font-medium">Complete the form to keep chatting.</p>
      <p className="mt-1 text-xs text-muted-foreground">
        You&rsquo;ve used your {EMBED_FREE_TURN_LIMIT} free questions. Fill in the
        short form to unlock more.
      </p>
    </div>
  );
}
