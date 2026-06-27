// Cloudflare Pages Function — POST /api/chat
// "Ask about the stack" docs chat for digithings.ai.
//
// The DigiVault-managed architecture vault is the ONLY knowledge source — no web
// search, no other tools. Retrieval is a Postgres full-text search over the vault
// hosted in Supabase (public.architecture_notes, synced from docs/vision/ by
// scripts/sync_architecture_vault.py). We call the search_architecture_notes RPC
// with the anon key (RLS-gated, read-only), inject the top hits as system context,
// and stream an OpenRouter free-model-pool completion back as plain-text deltas.
//
// Config (Pages env vars):
//   OPENROUTER_API_KEY      — required; the LLM call. Missing => clear 503.
//   CORE_SUPABASE_URL       — required; the vault's Supabase project URL.
//   CORE_SUPABASE_ANON_KEY  — required; anon key (public, RLS-gated read).
// No service-role key here: the Function only ever reads, through the anon RLS policy.

interface Env {
  OPENROUTER_API_KEY?: string;
  CORE_SUPABASE_URL?: string;
  CORE_SUPABASE_ANON_KEY?: string;
  // Optional KV for cross-isolate rate limiting; falls back to in-memory (soft).
  RATE_LIMIT_KV?: {
    get: (key: string) => Promise<string | null>;
    put: (key: string, value: string, opts?: { expirationTtl?: number }) => Promise<void>;
  };
}
interface EventContext {
  request: Request;
  env: Env;
  waitUntil?: (p: Promise<unknown>) => void;
}
interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}
interface VaultHit {
  vault_path: string;
  title: string;
  note_type: string;
  summary: string;
  body_markdown: string;
  tags: string[];
  wikilinks: string[];
  rank: number;
}

// ---- Tunables ----
const MAX_TURNS = 12; // conversation turns sent upstream
const MAX_MSG_CHARS = 2000; // cap a single message
const TOP_K = 6; // vault hits injected as context
const MAX_NOTE_CHARS = 1500; // truncate each note body — bounds prompt size/cost
const RATE_LIMIT_MAX = 20;
const RATE_LIMIT_WINDOW_S = 60;

// OpenRouter FREE-MODEL POOL (models[] fallback routing). `:free` membership churns —
// verify against https://openrouter.ai/models?max_price=0 before relying in prod.
const MODEL_POOL = [
  "meta-llama/llama-3.3-70b-instruct:free",
  "qwen/qwen-2.5-72b-instruct:free",
  "google/gemma-2-9b-it:free",
  "mistralai/mistral-7b-instruct:free",
];

const SYSTEM_PROMPT =
  "You are the DigiThings documentation assistant. Answer ONLY from the provided " +
  "DigiVault context about the open-core agentic stack (DigiGraph, DigiQuant, " +
  "DigiSearch, DigiChat, DigiKey, DigiSmith, DigiVault, DigiClaw, DigiBase, DigiLLM, " +
  "DigiFetch, DigiDev, DigiLink, DigiStore, Olympus). Be concise and technical. If the " +
  "context doesn't cover the question, say so plainly. Never invent features, ports, or APIs.";

function jsonError(message: string, status = 400): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function notConfigured(detail: string): Response {
  return new Response(JSON.stringify({ error: "chat not configured", detail }), {
    status: 503,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

// ---- Rate limiting (KV if bound, else best-effort in-memory per-isolate) ----
const memHits = new Map<string, { count: number; reset: number }>();
async function rateLimit(env: Env, ip: string): Promise<boolean> {
  const now = Date.now();
  if (env.RATE_LIMIT_KV) {
    const key = `rl:${ip}`;
    const raw = await env.RATE_LIMIT_KV.get(key);
    const count = raw ? parseInt(raw, 10) || 0 : 0;
    if (count >= RATE_LIMIT_MAX) return false;
    await env.RATE_LIMIT_KV.put(key, String(count + 1), { expirationTtl: RATE_LIMIT_WINDOW_S });
    return true;
  }
  const e = memHits.get(ip);
  if (!e || now > e.reset) {
    memHits.set(ip, { count: 1, reset: now + RATE_LIMIT_WINDOW_S * 1000 });
    return true;
  }
  if (e.count >= RATE_LIMIT_MAX) return false;
  e.count += 1;
  return true;
}

// ---- Same-site guard: cheap speed-bump vs cross-site/scripted abuse (Origin is
// spoofable; the real throttle is KV). Lenient on localhost for wrangler testing. ----
function sameSiteOK(request: Request): boolean {
  const reqHost = new URL(request.url).hostname;
  if (reqHost === "localhost" || reqHost === "127.0.0.1") return true;
  const origin = request.headers.get("origin");
  if (!origin) return false; // browsers send Origin on POST; absent => not a page request
  try {
    const o = new URL(origin).hostname;
    return o === reqHost || o.endsWith(".pages.dev");
  } catch {
    return false;
  }
}

// ---- Retrieval: FTS over the Supabase-hosted vault via the RPC (anon, RLS read) ----
async function searchVault(env: Env, query: string, k: number): Promise<VaultHit[]> {
  const base = (env.CORE_SUPABASE_URL ?? "").replace(/\/+$/, "");
  const key = env.CORE_SUPABASE_ANON_KEY ?? "";
  const resp = await fetch(`${base}/rest/v1/rpc/search_architecture_notes`, {
    method: "POST",
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ query, match_limit: k }),
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new Error(`vault search ${resp.status}: ${detail.slice(0, 200)}`);
  }
  return (await resp.json()) as VaultHit[];
}

function buildContext(hits: VaultHit[]): string {
  return hits
    .map((h) => {
      const body =
        h.body_markdown.length > MAX_NOTE_CHARS
          ? h.body_markdown.slice(0, MAX_NOTE_CHARS) + "\n…(truncated)"
          : h.body_markdown;
      return `## ${h.title} (${h.vault_path})\n${body}`;
    })
    .join("\n\n---\n\n");
}

// onRequestPost — Pages Functions route handler for POST /api/chat.
export async function onRequestPost(ctx: EventContext): Promise<Response> {
  const { request, env } = ctx;

  // 1. Config gates FIRST — never call upstreams half-configured.
  if (!env.OPENROUTER_API_KEY) {
    return notConfigured("OPENROUTER_API_KEY is not set on this deployment.");
  }
  if (!env.CORE_SUPABASE_URL || !env.CORE_SUPABASE_ANON_KEY) {
    return notConfigured("CORE_SUPABASE_URL / CORE_SUPABASE_ANON_KEY are not set — the vault is unreachable.");
  }

  // 1b. Same-site guard — reject cross-site / scripted callers before any work.
  if (!sameSiteOK(request)) return jsonError("forbidden: cross-site requests are not allowed", 403);

  // 2. Rate limit by client IP.
  const ip = request.headers.get("cf-connecting-ip") ?? "anon";
  if (!(await rateLimit(env, ip))) return jsonError("rate limit exceeded — slow down a moment", 429);

  // 3. Parse + sanitize body.
  let body: { messages?: ChatMessage[] };
  try {
    body = (await request.json()) as { messages?: ChatMessage[] };
  } catch {
    return jsonError("invalid JSON body");
  }
  const messages = Array.isArray(body.messages) ? body.messages : [];
  if (messages.length === 0) return jsonError("messages required");

  const clean: ChatMessage[] = messages
    .filter(
      (m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string",
    )
    .slice(-MAX_TURNS)
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_MSG_CHARS) }));
  const lastUser = [...clean].reverse().find((m) => m.role === "user");
  if (!lastUser) return jsonError("a user message is required");

  // 4. Retrieve from the vault (the only knowledge source).
  let context = "";
  try {
    context = buildContext(await searchVault(env, lastUser.content, TOP_K));
  } catch (e) {
    return jsonError(`vault unavailable: ${(e as Error).message}`, 502);
  }

  // 5. Compose upstream messages.
  const upstream: ChatMessage[] = [
    { role: "system", content: SYSTEM_PROMPT },
    {
      role: "system",
      content:
        "DigiVault context (answer ONLY from this; cite nothing outside it):\n\n" +
        (context || "(no relevant documentation found for this question)"),
    },
    ...clean,
  ];

  // 6. Call OpenRouter with the free-model pool + streaming.
  let orResp: Response;
  try {
    orResp = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
        "content-type": "application/json",
        "HTTP-Referer": "https://digithings.ai",
        "X-Title": "DigiThings Docs Assistant",
      },
      body: JSON.stringify({
        models: MODEL_POOL,
        messages: upstream,
        stream: true,
        temperature: 0.2,
        max_tokens: 700,
      }),
    });
  } catch (e) {
    return jsonError(`upstream request failed: ${(e as Error).message}`, 502);
  }
  if (!orResp.ok || !orResp.body) {
    const detail = await orResp.text().catch(() => "");
    return jsonError(`model pool error (${orResp.status}): ${detail.slice(0, 300)}`, 502);
  }

  // 7. Transform OpenRouter SSE → plain-text token stream the browser appends.
  const reader = orResp.body.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buf = "";
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        controller.close();
        return;
      }
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? ""; // keep the trailing partial line
      for (const line of lines) {
        const t = line.trim();
        if (!t.startsWith("data:")) continue;
        const payload = t.slice(5).trim();
        if (payload === "[DONE]") {
          controller.close();
          return;
        }
        try {
          const json = JSON.parse(payload);
          const delta: string | undefined = json?.choices?.[0]?.delta?.content;
          if (delta) controller.enqueue(encoder.encode(delta));
        } catch {
          // ignore non-JSON keepalive / ": OPENROUTER PROCESSING" comment frames
        }
      }
    },
    cancel() {
      reader.cancel().catch(() => {});
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}
