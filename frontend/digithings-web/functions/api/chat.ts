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
  error?: { message?: string; code?: number };
}
interface VaultHit {
  vault_path: string;
  title: string;
  body_markdown: string;
}

type ProviderId = "openrouter" | "openai" | "anthropic" | "gemini";

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
  | { type: "quota_exhausted"; message: string }
  | { type: "done" };

type OpenAiCompatRoute = {
  kind: "openai_compat";
  url: string;
  apiKey: string;
  model?: string;
  models?: string[];
  isFreePool: boolean;
  extraHeaders?: Record<string, string>;
};

type AnthropicRoute = {
  kind: "anthropic";
  apiKey: string;
  model: string;
};

type LlmRoute = OpenAiCompatRoute | AnthropicRoute;

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

const DEFAULT_BYOK_MODEL: Record<ProviderId, string> = {
  openrouter: "openai/gpt-4o-mini",
  openai: "gpt-4o-mini",
  anthropic: "claude-3-5-haiku-20241022",
  gemini: "gemini-2.5-flash",
};

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

const ANTHROPIC_TOOL = {
  name: "search_digivault",
  description: TOOLS[0].function.description,
  input_schema: TOOLS[0].function.parameters,
};

const NO_CONTENT_NOTE =
  "⚠ the model pool returned no content — the free models may be rate-limited or out of daily " +
  "quota. Please retry in a moment.";

const QUOTA_MESSAGE =
  "The free model pool is out of quota. Add your own API key to keep chatting.";

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

function validateByokKey(key: string, provider: ProviderId): string | null {
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
  }
  return null;
}

function resolveRoute(request: Request, env: Env, bodyModel?: string): LlmRoute | Response {
  const byokKey = request.headers.get("x-byok-key")?.trim() ?? "";
  const rawProvider = request.headers.get("x-byok-provider")?.trim() ?? "openrouter";
  const provider: ProviderId =
    rawProvider === "openai" ||
    rawProvider === "anthropic" ||
    rawProvider === "gemini" ||
    rawProvider === "openrouter"
      ? rawProvider
      : "openrouter";
  const model =
    bodyModel?.trim() ||
    request.headers.get("x-byok-model")?.trim() ||
    DEFAULT_BYOK_MODEL[provider];

  if (byokKey) {
    const err = validateByokKey(byokKey, provider);
    if (err) return jsonError(err, 400);

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

  if (!env.OPENROUTER_API_KEY) {
    return notConfigured(
      "OPENROUTER_API_KEY is not set — add your own key in chat settings to continue.",
    );
  }
  return {
    kind: "openai_compat",
    url: "https://openrouter.ai/api/v1/chat/completions",
    apiKey: env.OPENROUTER_API_KEY,
    models: MODEL_POOL,
    isFreePool: true,
    extraHeaders: {
      "HTTP-Referer": "https://digithings.ai",
      "X-Title": "digithings docs assistant",
    },
  };
}

function isQuotaStatus(status: number): boolean {
  return status === 402 || status === 429;
}

function parseUpstreamQuota(detail: string): boolean {
  const lower = detail.toLowerCase();
  return (
    lower.includes("quota") ||
    lower.includes("rate limit") ||
    lower.includes("rate_limit") ||
    lower.includes("insufficient") ||
    lower.includes("credits")
  );
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
const LLM_TIMEOUT_MS = 45_000;

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

function openAiHeaders(route: OpenAiCompatRoute): Record<string, string> {
  return {
    Authorization: `Bearer ${route.apiKey}`,
    "content-type": "application/json",
    ...route.extraHeaders,
  };
}

function openAiBody(
  route: OpenAiCompatRoute,
  messages: ConvoMessage[],
  opts: { stream: boolean; tools?: boolean },
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    messages,
    temperature: 0.2,
    max_tokens: 800,
    stream: opts.stream,
  };
  if (route.models?.length) {
    body.models = route.models;
    if (opts.tools) body.provider = { require_parameters: true };
  } else if (route.model) {
    body.model = route.model;
  }
  if (opts.tools) {
    body.tools = TOOLS;
    body.tool_choice = "auto";
  }
  return body;
}

class UpstreamError extends Error {
  constructor(
    message: string,
    readonly quota = false,
  ) {
    super(message);
  }
}

async function callOpenAiCompat(
  route: OpenAiCompatRoute,
  messages: ConvoMessage[],
): Promise<ChatCompletionResponse> {
  const resp = await fetchWithTimeout(
    route.url,
    {
      method: "POST",
      headers: openAiHeaders(route),
      body: JSON.stringify(openAiBody(route, messages, { stream: false, tools: true })),
    },
    LLM_TIMEOUT_MS,
  );
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    const quota = route.isFreePool && (isQuotaStatus(resp.status) || parseUpstreamQuota(detail));
    throw new UpstreamError(`upstream ${resp.status}: ${detail.slice(0, 300)}`, quota);
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

async function streamOpenAiCompat(
  route: OpenAiCompatRoute,
  messages: ConvoMessage[],
  emit: (ev: ChatStreamEvent) => void,
): Promise<string> {
  const resp = await fetchWithTimeout(
    route.url,
    {
      method: "POST",
      headers: openAiHeaders(route),
      body: JSON.stringify(openAiBody(route, messages, { stream: true })),
    },
    LLM_TIMEOUT_MS,
  );
  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => "");
    const quota = route.isFreePool && (isQuotaStatus(resp.status) || parseUpstreamQuota(detail));
    throw new UpstreamError(`upstream stream ${resp.status}: ${detail.slice(0, 300)}`, quota);
  }

  let content = "";
  for await (const json of iterateOpenAiSse(resp.body)) {
    const err = json.error as { message?: string } | undefined;
    if (err?.message) throw new UpstreamError(err.message, route.isFreePool);
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

type AnthropicBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string };

interface AnthropicMessage {
  role: "user" | "assistant";
  content: string | AnthropicBlock[];
}

function toAnthropicMessages(convo: ConvoMessage[]): {
  system: string;
  messages: AnthropicMessage[];
} {
  const systemParts: string[] = [];
  const messages: AnthropicMessage[] = [];

  for (const m of convo) {
    if (m.role === "system") {
      systemParts.push(m.content);
      continue;
    }
    if (m.role === "user") {
      messages.push({ role: "user", content: m.content });
      continue;
    }
    if (m.role === "assistant") {
      if (m.tool_calls?.length) {
        const blocks: AnthropicBlock[] = [];
        if (m.content) blocks.push({ type: "text", text: m.content });
        for (const tc of m.tool_calls) {
          let input: Record<string, unknown> = {};
          try {
            input = JSON.parse(tc.function.arguments || "{}") as Record<string, unknown>;
          } catch {
            /* keep empty */
          }
          blocks.push({
            type: "tool_use",
            id: tc.id,
            name: tc.function.name,
            input,
          });
        }
        messages.push({ role: "assistant", content: blocks });
      } else {
        messages.push({ role: "assistant", content: m.content });
      }
      continue;
    }
    if (m.role === "tool" && m.tool_call_id) {
      messages.push({
        role: "user",
        content: [{ type: "tool_result", tool_use_id: m.tool_call_id, content: m.content }],
      });
    }
  }
  return { system: systemParts.join("\n\n"), messages };
}

interface AnthropicResponse {
  content?: AnthropicBlock[];
  stop_reason?: string;
  error?: { message?: string };
}

function anthropicToAssistant(msg: AnthropicResponse): {
  content: string;
  tool_calls: ToolCall[];
} {
  const tool_calls: ToolCall[] = [];
  let content = "";
  for (const block of msg.content ?? []) {
    if (block.type === "text") content += block.text;
    if (block.type === "tool_use") {
      tool_calls.push({
        id: block.id,
        type: "function",
        function: {
          name: block.name,
          arguments: JSON.stringify(block.input ?? {}),
        },
      });
    }
  }
  return { content, tool_calls };
}

async function callAnthropic(route: AnthropicRoute, convo: ConvoMessage[]): Promise<{
  content: string;
  tool_calls: ToolCall[];
}> {
  const { system, messages } = toAnthropicMessages(convo);
  const resp = await fetchWithTimeout(
    "https://api.anthropic.com/v1/messages",
    {
      method: "POST",
      headers: {
        "x-api-key": route.apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: route.model,
        max_tokens: 800,
        system,
        messages,
        tools: [ANTHROPIC_TOOL],
        temperature: 0.2,
      }),
    },
    LLM_TIMEOUT_MS,
  );
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new UpstreamError(`anthropic ${resp.status}: ${detail.slice(0, 300)}`);
  }
  const data = (await resp.json()) as AnthropicResponse;
  if (data.error?.message) throw new UpstreamError(data.error.message);
  return anthropicToAssistant(data);
}

async function streamAnthropic(
  route: AnthropicRoute,
  convo: ConvoMessage[],
  emit: (ev: ChatStreamEvent) => void,
): Promise<string> {
  const { system, messages } = toAnthropicMessages(convo);
  const resp = await fetchWithTimeout(
    "https://api.anthropic.com/v1/messages",
    {
      method: "POST",
      headers: {
        "x-api-key": route.apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: route.model,
        max_tokens: 800,
        system,
        messages,
        temperature: 0.2,
        stream: true,
      }),
    },
    LLM_TIMEOUT_MS,
  );
  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => "");
    throw new UpstreamError(`anthropic stream ${resp.status}: ${detail.slice(0, 300)}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let content = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n")) !== -1) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line.startsWith("data: ")) continue;
      try {
        const json = JSON.parse(line.slice(6)) as {
          type?: string;
          delta?: { type?: string; text?: string };
        };
        if (json.type === "content_block_delta" && json.delta?.type === "text_delta") {
          const piece = json.delta.text ?? "";
          if (piece) {
            content += piece;
            emit({ type: "content", delta: piece });
          }
        }
      } catch {
        /* skip */
      }
    }
  }
  return content.trim();
}

async function callModel(
  route: LlmRoute,
  messages: ConvoMessage[],
): Promise<{ content: string; tool_calls: ToolCall[] }> {
  if (route.kind === "anthropic") {
    return callAnthropic(route, messages);
  }
  const data = await callOpenAiCompat(route, messages);
  if (data.error) {
    throw new UpstreamError(data.error.message ?? "model unavailable", route.isFreePool);
  }
  const msg = data.choices?.[0]?.message;
  return {
    content: msg?.content ?? "",
    tool_calls: msg?.tool_calls ?? [],
  };
}

async function streamFinalAnswer(
  route: LlmRoute,
  messages: ConvoMessage[],
  emit: (ev: ChatStreamEvent) => void,
): Promise<string> {
  if (route.kind === "anthropic") {
    return streamAnthropic(route, messages, emit);
  }
  return streamOpenAiCompat(route, messages, emit);
}

function emitQuotaIfFree(route: LlmRoute, emit: (ev: ChatStreamEvent) => void): void {
  if (route.kind === "openai_compat" && route.isFreePool) {
    emit({ type: "quota_exhausted", message: QUOTA_MESSAGE });
  }
}

async function runAgenticLoopStream(
  convo: ConvoMessage[],
  env: Env,
  route: LlmRoute,
  emit: (ev: ChatStreamEvent) => void,
): Promise<void> {
  const messages = [...convo];
  for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
    emit({
      type: "status",
      message: round === 0 ? "Thinking…" : "Reviewing digivault results…",
    });

    let msg: { content: string; tool_calls: ToolCall[] };
    try {
      msg = await callModel(route, messages);
    } catch (e) {
      const err = e as UpstreamError;
      console.error("model call failed:", err.message);
      if (err.quota) {
        emitQuotaIfFree(route, emit);
        emit({ type: "content", delta: NO_CONTENT_NOTE });
        return;
      }
      emit({ type: "error", message: "the model is temporarily unavailable — please retry" });
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

    try {
      const streamed = await streamFinalAnswer(route, messages, emit);
      if (!streamed) {
        emitQuotaIfFree(route, emit);
        emit({ type: "content", delta: NO_CONTENT_NOTE });
      }
    } catch (e) {
      const err = e as UpstreamError;
      if (err.quota) {
        emitQuotaIfFree(route, emit);
        emit({ type: "content", delta: NO_CONTENT_NOTE });
        return;
      }
      emit({ type: "error", message: "the model is temporarily unavailable — please retry" });
    }
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

  if (!env.CORE_SUPABASE_URL || !env.CORE_SUPABASE_ANON_KEY) {
    return notConfigured(
      "CORE_SUPABASE_URL / CORE_SUPABASE_ANON_KEY are not set — the vault is unreachable.",
    );
  }

  if (!sameSiteOK(request)) return jsonError("forbidden: cross-site requests are not allowed", 403);

  const ip = request.headers.get("cf-connecting-ip") ?? "anon";
  if (!(await rateLimit(env, ip))) return jsonError("rate limit exceeded — slow down a moment", 429);

  let body: { messages?: ChatMessage[]; model?: string };
  try {
    body = (await request.json()) as { messages?: ChatMessage[]; model?: string };
  } catch {
    return jsonError("invalid JSON body");
  }

  const route = resolveRoute(request, env, body.model);
  if (route instanceof Response) return route;

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
  return ndjsonResponse((emit) => runAgenticLoopStream(convo, env, route, emit));
}
