"use client";

/**
 * /embed — minimal unauthenticated chat surface for iframe embedding.
 *
 *   ?accent=digithings|digiquant|digichat   (default: digichat)
 *
 * Policy:
 *   - First N=EMBED_FREE_TURN_LIMIT (3) user turns are free.
 *   - After the limit, the gate card is shown with two CTAs:
 *     (1) reveal BYOK input → BYOK key unlocks unlimited turns in-place,
 *     (2) "Open DigiChat" → https://chat.digithings.ai.
 *   - BYOK key is stored via the shared useBYOKKey hook (localStorage),
 *     never duplicated.
 *
 * Frame-ancestors CSP is set in next.config.ts; this page assumes it is loaded
 * inside an iframe on digithings.ai / digiquant.io (or standalone for dev).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import { Send, Key, ExternalLink, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useBYOKKey,
  validateBYOKKey,
  validateBYOKModel,
  type BYOKProvider,
} from "@/hooks/use-byok-key";
import { formatEmbedChatError } from "@/lib/embed-chat-error";
import { p } from "@/lib/base-path";
import {
  emit,
  useEmbedGate,
  EMBED_FREE_TURN_LIMIT,
} from "@/lib/embed-gate";

type Accent = "digithings" | "digiquant" | "digichat";

const ACCENTS: readonly Accent[] = ["digithings", "digiquant", "digichat"];

function resolveAccent(raw: string | null | undefined): Accent {
  if (raw && (ACCENTS as readonly string[]).includes(raw)) return raw as Accent;
  return "digichat";
}

/**
 * Per-accent scoped overrides. We don't fork the whole token set — just
 * `--accent` (and the matching foreground). These colors mirror the
 * marketing-site brand hues; digichat keeps the neutral dark value from
 * globals.css's `.dark` block.
 *
 * Using CSS vars (not raw hex in JSX) per the unit's conventions; the inline
 * <style> lives in this page so the embed layout stays zero-dependency on
 * tokens.css (which #240 owns).
 */
const ACCENT_CSS = `
.accent-digithings { --accent: #7c3aed; --accent-foreground: #f5f3ff; }
.accent-digiquant  { --accent: #10b981; --accent-foreground: #ecfdf5; }
.accent-digichat   { --accent: #1f1f1f; --accent-foreground: #e6e6e6; }
`;

type EmbedPageProps = {
  searchParams: Promise<{ accent?: string }> | { accent?: string };
};

export default function EmbedPage({ searchParams }: EmbedPageProps) {
  const [accent, setAccent] = useState<Accent>("digichat");

  // Next 15/16: searchParams may be a Promise — resolve both shapes.
  useEffect(() => {
    let cancelled = false;
    Promise.resolve(searchParams).then((sp) => {
      if (cancelled) return;
      setAccent(resolveAccent(sp?.accent));
    });
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  useEffect(() => {
    emit("embed_loaded", { accent });
  }, [accent]);

  return (
    <>
      <style>{ACCENT_CSS}</style>
      <div className="dc-grain" aria-hidden />
      <div className={`dark accent-${accent} relative z-10 flex min-h-dvh flex-col`}>
        <EmbedChat accent={accent} />
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

function EmbedChat({ accent }: { accent: Accent }) {
  const { key: byokKey, provider: byokProvider, model: byokModel, isSet: byokIsSet } =
    useBYOKKey();
  const gate = useEmbedGate(byokIsSet);

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        // Reuses the main authenticated chat route. In production the embed
        // is expected to run with BYOK (unlimited) or behind a demo-session
        // cookie on the host site; the free-tier gate here is purely a
        // client-side UX affordance (per #241 non-goals: no backend rate
        // limiting).
        api: p("/api/chat"),
        prepareSendMessagesRequest: ({ messages, body }) => {
          const headers: Record<string, string> = {
            "content-type": "application/json",
            "X-Embed-Host": gate.host,
            "X-Embed-Accent": accent,
          };
          if (byokKey) {
            headers["X-BYOK-Key"] = byokKey;
            headers["X-BYOK-Provider"] = byokProvider;
            if (byokProvider === "openrouter" && byokModel.trim()) {
              headers["X-BYOK-Model"] = byokModel.trim();
            }
          }
          return {
            body: {
              ...(typeof body === "object" && body !== null ? body : {}),
              messages,
            },
            headers,
          };
        },
      }),
    [byokKey, byokProvider, byokModel, gate.host, accent],
  );

  const { messages, sendMessage, status, error, regenerate } = useChat<UIMessage>({
    transport,
  });
  const chatError = formatEmbedChatError(error);

  const [text, setText] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, status]);

  const busy = status === "streaming" || status === "submitted";

  const onSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const t = text.trim();
      if (!t || busy) return;
      if (gate.locked) return;

      sendMessage({
        role: "user",
        parts: [{ type: "text", text: t }],
      });
      emit("embed_turn_submitted", {
        accent,
        turn: gate.turns + 1,
        byok: byokIsSet,
      });
      gate.increment();
      setText("");
    },
    [text, busy, gate, sendMessage, accent, byokIsSet],
  );

  return (
    <>
      <header className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-sm font-semibold tracking-tight">DigiChat</span>
        <span
          className="text-[10px] uppercase tracking-wider text-muted-foreground"
          aria-label={`Turns used: ${gate.turns} of ${gate.limit}`}
        >
          {byokIsSet ? "BYOK unlocked" : `${gate.turns}/${gate.limit} free`}
        </span>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
        role="log"
        aria-live="polite"
      >
        {messages.length === 0 && !gate.locked && (
          <p className="text-sm text-muted-foreground">
            Ask a question to get started. The first {EMBED_FREE_TURN_LIMIT} are
            free.
          </p>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {chatError ? (
          <div
            className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            role="alert"
          >
            <p>{chatError}</p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-2"
              onClick={() => regenerate()}
            >
              Retry
            </Button>
          </div>
        ) : null}
      </div>

      {gate.locked ? (
        <PaywallCard />
      ) : (
        <form
          onSubmit={onSubmit}
          className="flex gap-2 border-t border-border p-3"
        >
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="ask digichat…"
            aria-label="Message"
            disabled={busy}
          />
          <Button
            type="submit"
            size="icon"
            disabled={busy || !text.trim()}
            aria-label="Send message"
            style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
          >
            <Send className="size-4" />
          </Button>
        </form>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Message bubble — plain text only, intentionally minimal.
// ---------------------------------------------------------------------------

function MessageBubble({ message }: { message: UIMessage }) {
  const text = message.parts
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("");
  const mine = message.role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          mine
            ? "bg-[color:var(--accent)] text-[color:var(--accent-foreground)]"
            : "bg-muted text-foreground"
        }`}
      >
        {text || <span className="opacity-60">…</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Paywall / BYOK reveal
// ---------------------------------------------------------------------------

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
