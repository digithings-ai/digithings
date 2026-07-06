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

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { useEmbedDigiChat } from "@/hooks/use-embed-digi-chat";
import {
  emit,
  useEmbedGate,
  EMBED_FREE_TURN_LIMIT,
} from "@/lib/embed-gate";
import { readEmbedUiParams } from "@/lib/embed-ui-params";
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

  const accentStyle = tenantCfg.accent
    ? ({
        "--accent": tenantCfg.accent.color,
        "--accent-foreground": tenantCfg.accent.foreground,
      } as React.CSSProperties)
    : undefined;

  return (
    <>
      <style>{ACCENT_CSS}</style>
      <div className="dc-grain" aria-hidden />
      <div
        className={`${tenantCfg.theme === "light" ? "light" : "dark"} accent-${accent} relative z-10 flex min-h-dvh flex-col bg-background text-foreground`}
        style={accentStyle}
      >
        <EmbedChat accent={accent} tenantCfg={tenantCfg} token={token} host={host} />
      </div>
    </>
  );
}

function EmbedChat({
  accent,
  tenantCfg,
  token,
  host,
}: {
  accent: Accent;
  tenantCfg: EmbedTenantClientConfig;
  token?: string;
  host?: string;
}) {
  const { key: byokKey, provider: byokProvider, model: byokModel, isSet: byokIsSet } =
    useBYOKKey();
  const ungated = tenantCfg.gateMode === "ungated";
  const showByok = !ungated;
  const gate = useEmbedGate(byokIsSet || ungated, host);

  const chat = useEmbedDigiChat({
    accent,
    token,
    host,
    embedHost: gate.host,
    byokKey: byokIsSet ? byokKey : undefined,
    byokProvider,
    byokModel,
  });

  const uiParams = useMemo(() => {
    if (typeof window === "undefined") return {};
    return readEmbedUiParams(window.location.search);
  }, []);

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
  const suggestions = uiParams.suggestions ?? tenantCfg.suggestions ?? [];
  const headerTitle = tenantCfg.title;

  const wrappedSend = useCallback(
    (question: string) => {
      if (gate.locked && !ungated) return;
      void chat.send(question);
      emit("embed_turn_submitted", {
        accent,
        turn: gate.turns + 1,
        byok: byokIsSet,
      });
      if (!ungated) gate.increment();
    },
    [chat, gate, ungated, accent, byokIsSet],
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
      formReplacement={gate.locked && !ungated ? <PaywallCard /> : undefined}
      showIntro={!gate.locked}
      ariaLabel={headerTitle ?? "digichat embed"}
    />
  );
}

function PaywallCard() {
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
            {(["openrouter", "openai", "anthropic"] as BYOKProvider[]).map((p) => (
              <Button
                key={p}
                type="button"
                size="sm"
                variant={provider === p ? "default" : "outline"}
                className="flex-1 capitalize"
                onClick={() => setProvider(p)}
              >
                {p === "openai" ? "OpenAI" : p === "anthropic" ? "Anthropic" : "OpenRouter"}
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
