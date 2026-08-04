/**
 * Digivault LLM route resolution — free OpenRouter pool + full BYOK parity
 * with the Cloudflare digivault chat Function (OpenRouter / OpenAI / Anthropic / Gemini).
 */

export type ProviderId = "openrouter" | "openai" | "anthropic" | "gemini";

export const MODEL_POOL = [
  "openai/gpt-oss-120b:free",
  "meta-llama/llama-3.3-70b-instruct:free",
  "openai/gpt-oss-20b:free",
] as const;

export const DEFAULT_BYOK_MODEL: Record<ProviderId, string> = {
  openrouter: "openai/gpt-4o-mini",
  openai: "gpt-4o-mini",
  anthropic: "claude-3-5-haiku-20241022",
  gemini: "gemini-2.5-flash",
};

export const QUOTA_MESSAGE =
  "The free model pool is out of quota. Add your own API key to keep chatting.";

export type OpenAiCompatRoute = {
  kind: "openai_compat";
  url: string;
  apiKey: string;
  model?: string;
  models?: readonly string[];
  isFreePool: boolean;
  extraHeaders?: Record<string, string>;
};

export type AnthropicRoute = {
  kind: "anthropic";
  apiKey: string;
  model: string;
};

export type LlmRoute = OpenAiCompatRoute | AnthropicRoute;

export type ResolveDigivaultLlmRouteOpts = {
  byokKey?: string;
  byokProvider?: string;
  byokModel?: string;
  openRouterKey: string;
};

export type ResolveDigivaultLlmRouteResult =
  | LlmRoute
  | { error: string; status: 400 | 503 };

function normalizeProvider(raw: string | undefined): ProviderId {
  if (raw === "openai" || raw === "anthropic" || raw === "gemini" || raw === "openrouter") {
    return raw;
  }
  return "openrouter";
}

/** Returns null if valid, or a presentation-safe error (never echoes key material). */
export function validateDigivaultByokKey(key: string, provider: ProviderId): string | null {
  if (!key) return "API key is required.";
  switch (provider) {
    case "openrouter":
      if (!key.startsWith("sk-or-")) return "OpenRouter keys start with sk-or-.";
      break;
    case "openai":
      if (!key.startsWith("sk-")) return "OpenAI keys start with sk-.";
      break;
    case "anthropic":
      if (!key.startsWith("sk-ant-")) return "Anthropic keys start with sk-ant-.";
      break;
    case "gemini":
      if (!key.startsWith("AI")) return "Gemini keys start with AI.";
      break;
    default: {
      const _exhaustive: never = provider;
      void _exhaustive;
      return "Unsupported provider.";
    }
  }
  return null;
}

export function resolveDigivaultLlmRoute(
  opts: ResolveDigivaultLlmRouteOpts,
): ResolveDigivaultLlmRouteResult {
  const byokKey = opts.byokKey?.trim() ?? "";
  const provider = normalizeProvider(opts.byokProvider);
  const model = opts.byokModel?.trim() || DEFAULT_BYOK_MODEL[provider];

  if (byokKey) {
    const err = validateDigivaultByokKey(byokKey, provider);
    if (err) return { error: err, status: 400 };

    if (provider === "anthropic") {
      return { kind: "anthropic", apiKey: byokKey, model };
    }
    if (provider === "openai") {
      return {
        kind: "openai_compat",
        url: "https://api.openai.com/v1/chat/completions",
        apiKey: byokKey,
        model,
        isFreePool: false,
      };
    }
    if (provider === "gemini") {
      return {
        kind: "openai_compat",
        url: "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        apiKey: byokKey,
        model,
        isFreePool: false,
      };
    }
    return {
      kind: "openai_compat",
      url: "https://openrouter.ai/api/v1/chat/completions",
      apiKey: byokKey,
      model,
      isFreePool: false,
      extraHeaders: {
        "HTTP-Referer": "https://digithings.ai",
        "X-Title": "digithings docs assistant",
      },
    };
  }

  if (!opts.openRouterKey.trim()) {
    return {
      error: "chat not configured",
      status: 503,
    };
  }

  return {
    kind: "openai_compat",
    url: "https://openrouter.ai/api/v1/chat/completions",
    apiKey: opts.openRouterKey,
    models: MODEL_POOL,
    isFreePool: true,
    extraHeaders: {
      "HTTP-Referer": "https://digithings.ai",
      "X-Title": "digithings docs assistant",
    },
  };
}
