// Cloudflare Pages Function — POST /api/chat
// Agentic digivault chat: NDJSON stream with tool/status/reasoning/content events.

interface Env {
  OPENROUTER_API_KEY?: string;
  CORE_SUPABASE_URL?: string;
  CORE_SUPABASE_ANON_KEY?: string;
  RATE_LIMIT_KV?: {
    get: (key: string) => Promise<string | null>;
    put: (key: string, value: string, opts?: { expirationTtl?: number }) => Promise<void>;
  };
}
interface EventContext {
  request: Request;
  env: Env;
}
interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}
interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}
interface ConvoMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}
interface ChatCompletionResponse {
  choices?: Array<{
    message?: { role?: string; content?: string | null; tool_calls?: ToolCall[] };
  }>;
  error?: { message?: string };
}
interface VaultHit {
  vault_path: string;
  title: string;
  body_markdown: string;
}

type ChatStreamEvent =
  | { type: "status"; message: string }
  | { type: "tool_call"; name: string; query: string }
  | {
      type: "tool_result";
      name: string;
      query: string;
      hits: Array<{ title: string; path: string }>;
      count: number;
    }
  | { type: "reasoning"; delta: string }
  | { type: "content"; delta: string }
  | { type: "error"; message: string }
  | { type: "done" };

const MAX_TURNS = 12;
const MAX_MSG_CHARS = 2000;
const TOP_K = 4;
const MAX_NOTE_CHARS = 1200;
const MAX_TOOL_ROUNDS = 3;
const RATE_LIMIT_MAX = 60;
const RATE_LIMIT_WINDOW_S = 60;
const CHAT_STREAM_MIME = "application/x-ndjson; charset=utf-8";

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

function sameSiteOK(request: Request): boolean {
  const reqHost = new URL(request.url).hostname;
  if (reqHost === "localhost" || reqHost === "127.0.0.1") return true;
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).hostname === reqHost;
  } catch {
    return false;
  }
}

const VAULT_TIMEOUT_MS = 10_000;
const OPENROUTER_TIMEOUT_MS = 45_000;

async function fetchWithTimeout(url: string, init: RequestInit, ms: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

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

function parseToolQuery(rawArgs: string): string {
  try {
    const parsed = JSON.parse(rawArgs || "{}") as { query?: unknown };
    if (typeof parsed.query === "string") return parsed.query.trim();
  } catch {
    /* malformed */
  }
  return "";
}

async function runVaultTool(
  env: Env,
  name: string,
  rawArgs: string,
): Promise<{ text: string; hits: VaultHit[]; query: string }> {
  const query = parseToolQuery(rawArgs);
  if (name !== "search_digivault") {
    return { text: `Unknown tool: ${name}`, hits: [], query };
  }
  if (!query) {
    return { text: "No search query was provided.", hits: [], query: "" };
  }
  try {
    const hits = await searchVault(env, query, TOP_K);
    if (!hits.length) {
      return {
        text: "No matching documentation was found in the digivault for that query.",
        hits: [],
        query,
      };
    }
    return { text: buildContext(hits), hits, query };
  } catch (e) {
    console.error("digivault tool failed:", (e as Error).message);
    return {
      text: "The digivault is temporarily unavailable — tell the user to try again shortly.",
      hits: [],
      query,
    };
  }
}

function openRouterHeaders(apiKey: string): Record<string, string> {
  return {
    Authorization: `Bearer ${apiKey}`,
    "content-type": "application/json",
    "HTTP-Referer": "https://digithings.ai",
    "X-Title": "digithings docs assistant",
  };
}

async function callModel(env: Env, messages: ConvoMessage[]): Promise<ChatCompletionResponse> {
  const resp = await fetchWithTimeout(
    "https://openrouter.ai/api/v1/chat/completions",
    {
      method: "POST",
      headers: openRouterHeaders(env.OPENROUTER_API_KEY ?? ""),
      body: JSON.stringify({
        models: MODEL_POOL,
        messages,
        tools: TOOLS,
        tool_choice: "auto",
        provider: { require_parameters: true },
        temperature: 0.2,
        max_tokens: 800,
        stream: false,
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

async function* iterateOpenAiSse(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<Record<string, unknown>> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") return;
        try {
          yield JSON.parse(raw) as Record<string, unknown>;
        } catch {
          /* skip */
        }
      }
    }
  }
}

async function streamFinalAnswer(
  env: Env,
  messages: ConvoMessage[],
  emit: (ev: ChatStreamEvent) => void,
): Promise<string> {
  const resp = await fetchWithTimeout(
    "https://openrouter.ai/api/v1/chat/completions",
    {
      method: "POST",
      headers: openRouterHeaders(env.OPENROUTER_API_KEY ?? ""),
      body: JSON.stringify({
        models: MODEL_POOL,
        messages,
        temperature: 0.2,
        max_tokens: 800,
        stream: true,
      }),
    },
    OPENROUTER_TIMEOUT_MS,
  );
  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => "");
    throw new Error(`openrouter stream ${resp.status}: ${detail.slice(0, 300)}`);
  }

  let content = "";
  for await (const json of iterateOpenAiSse(resp.body)) {
    const err = json.error as { message?: string } | undefined;
    if (err?.message) throw new Error(err.message);
    const delta = (json.choices as Array<{ delta?: Record<string, unknown> }> | undefined)?.[0]
      ?.delta;
    if (!delta) continue;
    const reasoning = delta.reasoning_content ?? delta.reasoning;
    if (typeof reasoning === "string" && reasoning.length) {
      emit({ type: "reasoning", delta: reasoning });
    }
    const piece = delta.content;
    if (typeof piece === "string" && piece.length) {
      content += piece;
      emit({ type: "content", delta: piece });
    }
  }
  return content.trim();
}

async function runAgenticLoopStream(
  convo: ConvoMessage[],
  env: Env,
  emit: (ev: ChatStreamEvent) => void,
): Promise<void> {
  const messages = [...convo];
  for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
    emit({
      type: "status",
      message: round === 0 ? "Thinking…" : "Reviewing digivault results…",
    });

    let data: ChatCompletionResponse;
    try {
      data = await callModel(env, messages);
    } catch (e) {
      console.error("model call failed:", (e as Error).message);
      emit({ type: "error", message: "the model pool is temporarily unavailable — please retry" });
      return;
    }
    if (data.error) {
      emit({ type: "error", message: `upstream: ${data.error.message ?? "model unavailable"}` });
      return;
    }

    const msg = data.choices?.[0]?.message;
    if (!msg) {
      emit({ type: "content", delta: NO_CONTENT_NOTE });
      return;
    }

    const toolCalls = msg.tool_calls ?? [];
    if (toolCalls.length > 0) {
      messages.push({ role: "assistant", content: msg.content ?? "", tool_calls: toolCalls });
      for (const tc of toolCalls) {
        const name = tc.function?.name ?? "search_digivault";
        const rawArgs = tc.function?.arguments ?? "";
        const query = parseToolQuery(rawArgs) || "(unspecified)";
        emit({ type: "tool_call", name, query });
        emit({ type: "status", message: "Searching digivault…" });
        const result = await runVaultTool(env, name, rawArgs);
        emit({
          type: "tool_result",
          name,
          query: result.query || query,
          hits: result.hits.map((h) => ({ title: h.title, path: h.vault_path })),
          count: result.hits.length,
        });
        messages.push({ role: "tool", tool_call_id: tc.id, content: result.text });
      }
      continue;
    }

    emit({ type: "status", message: "Writing answer…" });
    const prefilled = (msg.content ?? "").trim();
    if (prefilled) {
      emit({ type: "content", delta: prefilled });
      return;
    }

    const streamed = await streamFinalAnswer(env, messages, emit);
    if (!streamed) emit({ type: "content", delta: NO_CONTENT_NOTE });
    return;
  }

  emit({
    type: "content",
    delta: "⚠ I couldn't finish that within a few steps — please rephrase or try again.",
  });
}

function ndjsonResponse(run: (emit: (ev: ChatStreamEvent) => void) => Promise<void>): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const emit = (ev: ChatStreamEvent) => {
        controller.enqueue(encoder.encode(`${JSON.stringify(ev)}\n`));
      };
      try {
        await run(emit);
        emit({ type: "done" });
      } catch (e) {
        console.error("chat stream failed:", (e as Error).message);
        emit({ type: "error", message: "chat failed unexpectedly — please retry" });
      } finally {
        controller.close();
      }
    },
  });
  return new Response(stream, {
    headers: {
      "content-type": CHAT_STREAM_MIME,
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

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

  if (!env.OPENROUTER_API_KEY) {
    return notConfigured("OPENROUTER_API_KEY is not set on this deployment.");
  }
  if (!env.CORE_SUPABASE_URL || !env.CORE_SUPABASE_ANON_KEY) {
    return notConfigured(
      "CORE_SUPABASE_URL / CORE_SUPABASE_ANON_KEY are not set — the vault is unreachable.",
    );
  }

  if (!sameSiteOK(request)) return jsonError("forbidden: cross-site requests are not allowed", 403);

  const ip = request.headers.get("cf-connecting-ip") ?? "anon";
  if (!(await rateLimit(env, ip))) return jsonError("rate limit exceeded — slow down a moment", 429);

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

  const convo: ConvoMessage[] = [{ role: "system", content: SYSTEM_PROMPT }, ...clean];
  return ndjsonResponse((emit) => runAgenticLoopStream(convo, env, emit));
}
