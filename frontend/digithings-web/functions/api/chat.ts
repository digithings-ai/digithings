// Cloudflare Pages Function — POST /api/chat
// digichat: the agentic "ask about the stack" assistant for digithings.ai.
//
// AGENTIC, not forced-RAG. The model drives the conversation and has exactly ONE tool —
// search_digivault — which full-text-searches the digivault (the only knowledge source about
// digithings). The model calls the tool when it needs facts about the stack, and answers casual
// chat directly without it. Retrieval is a Postgres FTS over the vault hosted in Supabase
// (public.architecture_notes, synced from docs/vision/ by scripts/sync_architecture_vault.py),
// queried with the anon key (RLS-gated, read-only). The local digivault MCP server is loopback
// only and unreachable from Cloudflare's edge, so the tool reads the same vault content from its
// public Supabase mirror.
//
// Every OpenRouter call is awaited inside handleChat (stream=false), so the top-level try/catch +
// fetchWithTimeout cover all failure modes and the endpoint returns proper HTTP status codes —
// it can never fail with an opaque raw Cloudflare 502, and there is no post-return stream to drop.
//
// Config (Pages env vars):
//   OPENROUTER_API_KEY      — required; the LLM calls. Missing => clear 503.
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
// A single inbound chat turn from the browser.
interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}
// OpenAI-shape tool call (as OpenRouter returns it on message.tool_calls).
interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}
// A message in the agentic conversation we send upstream — a superset of ChatMessage that also
// carries an assistant turn's tool_calls and the role:"tool" results that answer them.
interface ConvoMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}
// The (stream=false) chat-completions response shape we read.
interface ChatCompletionResponse {
  choices?: Array<{
    message?: { role?: string; content?: string | null; tool_calls?: ToolCall[] };
    finish_reason?: string;
  }>;
  error?: { message?: string };
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
const TOP_K = 4; // vault hits returned to the model per tool call (small — free models, small ctx)
const MAX_NOTE_CHARS = 1200; // truncate each note body — bounds the tool-result payload size
const MAX_TOOL_ROUNDS = 3; // model⇄tool round trips before we stop (bounds worst-case latency)
// Generous per-IP cap: humans never approach it; it only blunts bot floods. The chat runs on
// OpenRouter FREE models (no cost), so this deters spam rather than rationing real use.
const RATE_LIMIT_MAX = 60;
const RATE_LIMIT_WINDOW_S = 60;

// OpenRouter FREE-MODEL pool via the `models[]` fallback array — OpenRouter tries them in order,
// advancing to the next on error. These are led by tool-calling-capable free models (gpt-oss and
// llama-3.3-70b natively support function calling); combined with provider.require_parameters
// below, OpenRouter only routes to a model that actually supports the tools we send, and skips any
// that don't. `:free` membership churns; if these go stale, callModel surfaces the error to the
// user instead of going silently empty. NB free-tier limits are ACCOUNT-WIDE: 20 req/min, and
// 50 req/DAY unless the account has ever purchased >= $10 of credits (permanent -> 1000/day).
const MODEL_POOL = [
  "openai/gpt-oss-120b:free",
  "meta-llama/llama-3.3-70b-instruct:free",
  "openai/gpt-oss-20b:free",
];

const SYSTEM_PROMPT =
  "You are digichat, the documentation assistant for the digithings open-core agentic stack. " +
  "You have ONE tool, search_digivault, which queries the digivault — the only source of truth " +
  "about digithings. For ANY question about digithings, its modules, architecture, ports, APIs, " +
  "or how it is built or run, you MUST call search_digivault first and answer ONLY from what it " +
  "returns. If the tool returns nothing relevant, say you don't have that in the docs — never " +
  "invent features, ports, or APIs. For greetings or small talk unrelated to digithings, reply " +
  "normally without the tool. Be concise and technical. Always write digithings module names in " +
  "lowercase (digithings, digigraph, digichat, …); Olympus, Atlas, and Hermes keep their " +
  "capitalization.";

// The one tool the model is given. Its description is the model's cue for WHEN to reach for the
// vault vs. answer casual chat directly.
const TOOLS = [
  {
    type: "function" as const,
    function: {
      name: "search_digivault",
      description:
        "Search the digithings architecture knowledge base (the digivault docs) for facts about " +
        "the open-core stack: the modules (digigraph, digiquant, digisearch, digichat, digikey, " +
        "digismith, digivault, digiclaw, digibase) and roadmap ones (digistore, digilink), their " +
        "ports, APIs, how they connect, and how the system is built and run. Call this whenever " +
        "the user asks anything about digithings, its modules, architecture, or how it works. Do " +
        "NOT call it for greetings or small talk unrelated to digithings.",
      parameters: {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "What to look up in the digivault docs (a focused natural-language query).",
          },
        },
        required: ["query"],
      },
    },
  },
];

// Shown (as the answer body) when a model call succeeds at the HTTP level but yields no usable
// content — almost always the free pool being rate-limited / out of daily quota.
const NO_CONTENT_NOTE =
  "⚠ the model pool returned no content — the free models may be rate-limited or out of daily " +
  "quota. Please retry in a moment.";

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

// The successful answer body: plain text the browser appends. Non-streamed — the full answer
// arrives at once; the UI's "retrieving…" indicator covers the wait.
function answerText(text: string): Response {
  return new Response(text, {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

// ---- Rate limiting — best-effort bot deterrence, NOT a hard quota. The chat runs on
// OpenRouter FREE models (no cost), so the goal is to blunt spam, not ration real use; the
// per-IP cap is generous and the same-site guard is the primary deterrent. Binding
// RATE_LIMIT_KV makes the cap durable across Cloudflare isolates (RECOMMENDED, optional);
// without it the in-memory fallback is per-isolate (soft). Worst case under abuse without
// KV: temporary OpenRouter free-quota exhaustion — no cost, self-resolves. Fixed 60s
// window (epoch in the key, so the TTL isn't refreshed under load). ----
const memHits = new Map<string, { count: number; reset: number }>();
async function rateLimit(env: Env, ip: string): Promise<boolean> {
  const now = Date.now();
  if (env.RATE_LIMIT_KV) {
    const epoch = Math.floor(now / 1000 / RATE_LIMIT_WINDOW_S);
    const key = `rl:${ip}:${epoch}`;
    const count = parseInt((await env.RATE_LIMIT_KV.get(key)) ?? "0", 10) || 0;
    if (count >= RATE_LIMIT_MAX) return false;
    await env.RATE_LIMIT_KV.put(key, String(count + 1), { expirationTtl: RATE_LIMIT_WINDOW_S * 2 });
    return true;
  }
  // In-memory fallback (per-isolate, soft). Sweep expired entries so it can't grow unbounded.
  if (memHits.size > 5000) {
    for (const [k, v] of memHits) if (now > v.reset) memHits.delete(k);
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

// ---- Same-site guard: a speed-bump vs cross-site/scripted abuse (Origin is spoofable;
// the durable throttle is the KV limiter above). Same-origin only — the page's Origin
// must match the request host. Covers prod (digithings.ai) and any *.pages.dev preview
// (a preview page's Origin == its own host); a different *.pages.dev cannot clear it.
// Lenient on localhost for wrangler testing. ----
function sameSiteOK(request: Request): boolean {
  const reqHost = new URL(request.url).hostname;
  if (reqHost === "localhost" || reqHost === "127.0.0.1") return true;
  const origin = request.headers.get("origin");
  if (!origin) return false; // browsers send Origin on POST; absent => not a page request
  try {
    return new URL(origin).hostname === reqHost;
  } catch {
    return false;
  }
}

// Upstream fetch deadline. Without it, a hung Supabase/OpenRouter call makes the Worker wait
// until Cloudflare kills it with an opaque raw 502; with it, a slow/hung upstream surfaces as our
// own clean JSON error instead.
const VAULT_TIMEOUT_MS = 10_000;
const OPENROUTER_TIMEOUT_MS = 30_000;

async function fetchWithTimeout(url: string, init: RequestInit, ms: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

// ---- The search_digivault tool: FTS over the Supabase-hosted vault via the RPC (anon, RLS read) ----
async function searchVault(env: Env, query: string, k: number): Promise<VaultHit[]> {
  const base = (env.CORE_SUPABASE_URL ?? "").replace(/\/+$/, "");
  const key = env.CORE_SUPABASE_ANON_KEY ?? "";
  const resp = await fetchWithTimeout(
    `${base}/rest/v1/rpc/search_architecture_notes`,
    {
      method: "POST",
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ query, match_limit: k }),
    },
    VAULT_TIMEOUT_MS,
  );
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

// Execute a tool call by name and return a string the model reads back. Tool failures return a
// readable string (never throw) so the model can tell the user gracefully and the loop continues.
async function runTool(env: Env, name: string, rawArgs: string): Promise<string> {
  if (name !== "search_digivault") return `Unknown tool: ${name}`;
  let query = "";
  try {
    const parsed = JSON.parse(rawArgs || "{}") as { query?: unknown };
    if (typeof parsed.query === "string") query = parsed.query.trim();
  } catch {
    // malformed arguments — fall through to the empty-query message
  }
  if (!query) return "No search query was provided.";
  try {
    const hits = await searchVault(env, query, TOP_K);
    if (!hits.length) return "No matching documentation was found in the digivault for that query.";
    return buildContext(hits);
  } catch (e) {
    console.error("digivault tool failed:", (e as Error).message);
    return "The digivault is temporarily unavailable — tell the user to try again shortly.";
  }
}

// One non-streamed OpenRouter call with the free-model pool + the search_digivault tool. Throws on
// transport/HTTP failure so the caller can return a proper error status.
async function callModel(env: Env, messages: ConvoMessage[]): Promise<ChatCompletionResponse> {
  const resp = await fetchWithTimeout(
    "https://openrouter.ai/api/v1/chat/completions",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
        "content-type": "application/json",
        "HTTP-Referer": "https://digithings.ai",
        "X-Title": "digithings docs assistant",
      },
      body: JSON.stringify({
        models: MODEL_POOL,
        messages,
        tools: TOOLS,
        tool_choice: "auto",
        // Only route to a model that actually supports the tools we send; skip any that would
        // silently ignore them. The pairing of this with `tools` is what makes a flaky/non-tool
        // free model get bypassed instead of returning a toolless (hallucinated) answer.
        provider: { require_parameters: true },
        temperature: 0.2,
        max_tokens: 800,
      }),
    },
    OPENROUTER_TIMEOUT_MS,
  );
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new Error(`openrouter ${resp.status}: ${detail.slice(0, 300)}`);
  }
  return (await resp.json()) as ChatCompletionResponse;
}

export type LoopResult = { kind: "answer"; text: string } | { kind: "error"; message: string };

// The agentic loop, dependency-injected so it can be unit-tested without a network or a key:
// callModelFn returns a completion; runToolFn executes a tool by (name, args). The injection is
// the seam — feeding scripted completions exercises every branch (tool-call→answer, casual,
// error, empty, max-rounds) offline. Drives model⇄tool round trips until the model answers with
// no tool call,
// bounded by maxRounds. Hard upstream failures -> {error} (caller returns a real HTTP error);
// soft "no content" -> {answer} carrying a readable ⚠ note (surfaced, never a silent blank).
export async function runAgenticLoop(
  convo: ConvoMessage[],
  callModelFn: (messages: ConvoMessage[]) => Promise<ChatCompletionResponse>,
  runToolFn: (name: string, args: string) => Promise<string>,
  maxRounds: number = MAX_TOOL_ROUNDS,
): Promise<LoopResult> {
  const messages = [...convo];
  for (let round = 0; round < maxRounds; round++) {
    let data: ChatCompletionResponse;
    try {
      data = await callModelFn(messages);
    } catch (e) {
      console.error("model call failed:", (e as Error).message);
      return { kind: "error", message: "the model pool is temporarily unavailable — please retry" };
    }
    if (data.error) {
      console.error("openrouter error frame:", JSON.stringify(data.error).slice(0, 300));
      return { kind: "error", message: `upstream: ${data.error.message ?? "model unavailable"}` };
    }
    const msg = data.choices?.[0]?.message;
    if (!msg) return { kind: "answer", text: NO_CONTENT_NOTE };

    const toolCalls = msg.tool_calls ?? [];
    if (toolCalls.length > 0) {
      // Record the assistant's tool-call turn. content "" (not null) — some providers reject null.
      messages.push({ role: "assistant", content: msg.content ?? "", tool_calls: toolCalls });
      for (const tc of toolCalls) {
        const out = await runToolFn(tc.function?.name ?? "", tc.function?.arguments ?? "");
        messages.push({ role: "tool", tool_call_id: tc.id, content: out });
      }
      continue; // let the model read the results and answer (or call again)
    }

    const text = (msg.content ?? "").trim();
    return { kind: "answer", text: text || NO_CONTENT_NOTE };
  }
  return {
    kind: "answer",
    text: "⚠ I couldn't finish that within a few steps — please rephrase or try again.",
  };
}

// onRequestPost — Pages Functions route handler for POST /api/chat. A top-level guard turns ANY
// unhandled throw into our JSON 500 (readable in the browser Network tab) instead of an opaque
// Cloudflare raw 502 — so the endpoint can never fail silently at the edge.
export async function onRequestPost(ctx: EventContext): Promise<Response> {
  try {
    return await handleChat(ctx);
  } catch (e) {
    console.error("chat handler crashed:", (e as Error).stack ?? (e as Error).message);
    return jsonError("chat failed unexpectedly — please retry", 500);
  }
}

async function handleChat(ctx: EventContext): Promise<Response> {
  const { request, env } = ctx;

  // 1. Config gates FIRST — never call upstreams half-configured.
  if (!env.OPENROUTER_API_KEY) {
    return notConfigured("OPENROUTER_API_KEY is not set on this deployment.");
  }
  if (!env.CORE_SUPABASE_URL || !env.CORE_SUPABASE_ANON_KEY) {
    return notConfigured(
      "CORE_SUPABASE_URL / CORE_SUPABASE_ANON_KEY are not set — the vault is unreachable.",
    );
  }

  // 1b. Same-site guard — reject cross-site / scripted callers before any work.
  if (!sameSiteOK(request)) return jsonError("forbidden: cross-site requests are not allowed", 403);

  // 2. Rate limit by client IP — best-effort bot deterrence (see rateLimit); never hard-fails the
  // endpoint, since the chat runs on free models with no cost to ration.
  const ip = request.headers.get("cf-connecting-ip") ?? "anon";
  if (!(await rateLimit(env, ip))) return jsonError("rate limit exceeded — slow down a moment", 429);

  // 3. Parse + sanitize body.
  let body: { messages?: ChatMessage[] };
  try {
    body = (await request.json()) as { messages?: ChatMessage[] };
  } catch {
    return jsonError("invalid JSON body");
  }
  const inbound = Array.isArray(body.messages) ? body.messages : [];
  if (inbound.length === 0) return jsonError("messages required");

  const clean = inbound
    .filter(
      (m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string",
    )
    .slice(-MAX_TURNS)
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_MSG_CHARS) }));
  if (!clean.some((m) => m.role === "user")) return jsonError("a user message is required");

  // 4. Run the agentic loop: the model chats and calls search_digivault when it needs facts.
  const convo: ConvoMessage[] = [{ role: "system", content: SYSTEM_PROMPT }, ...clean];
  const result = await runAgenticLoop(
    convo,
    (messages) => callModel(env, messages),
    (name, args) => runTool(env, name, args),
  );

  if (result.kind === "error") return jsonError(result.message, 502);
  return answerText(result.text);
}
