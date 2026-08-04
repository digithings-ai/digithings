/**
 * Digivault LLM helpers — OpenAI-compat + Anthropic calls for the agentic loop.
 * Ported from frontend/digithings-web/functions/api/chat.ts.
 */

import type { AnthropicRoute, OpenAiCompatRoute, LlmRoute } from "./digivault-byok";

export const MAX_TOOL_ROUNDS = 3;

export const SYSTEM_PROMPT = [
  "You are digichat, the documentation assistant for the digithings open-core agentic stack.",
  "",
  "You have ONE tool: search_digivault. It queries the digivault — the only source of truth about digithings.",
  "",
  "Every turn you MUST follow exactly ONE of these two paths:",
  "",
  "PATH A — Direct answer (no tool):",
  "For greetings, small talk, or questions clearly unrelated to digithings architecture/docs.",
  "Reply directly with helpful content. Do NOT call search_digivault.",
  "",
  "PATH B — Tool call, then answer from results:",
  "For ANY question about digithings, its modules, architecture, ports, APIs, build/run, or how the system works:",
  "1. In the same turn, MUST emit a structured search_digivault tool_call with a focused query.",
  "2. After tool results return, answer ONLY from those results (summarize/cite). Never invent features, ports, or APIs.",
  "3. If the tool returns nothing relevant, say you don't have that in the docs.",
  "",
  "FORBIDDEN (broken third path):",
  "- Reasoning about needing to search without emitting a structured search_digivault tool_call.",
  "- Returning empty content or reasoning-only output with no user-visible answer.",
  "- Answering digithings questions from memory instead of calling the tool first.",
  "",
  "Be concise and technical. Write digithings module names in lowercase (digithings, digigraph, digichat, …);",
  "keep Olympus, Atlas, and Hermes capitalized.",
].join("\n");

export const TOOLS = [
  {
    type: "function" as const,
    function: {
      name: "search_digivault",
      description:
        "PATH B tool — search the digithings architecture knowledge base (digivault) for facts about " +
        "the open-core stack: modules (digigraph, digiquant, digisearch, digichat, digikey, " +
        "digismith, digivault, digiclaw, digibase) and roadmap ones (digistore, digilink), ports, " +
        "APIs, connections, build/run. REQUIRED for any digithings-related question: emit this " +
        "structured tool_call in the same turn (do not only reason about searching). Do NOT use " +
        "for PATH A (greetings or small talk unrelated to digithings).",
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

export type ToolCall = {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
};

export type ConvoMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
};

export class UpstreamError extends Error {
  constructor(
    message: string,
    readonly quota = false,
  ) {
    super(message);
    this.name = "UpstreamError";
  }
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
  opts: { stream: boolean; tools?: boolean; forceTool?: string },
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
    body.tool_choice = opts.forceTool
      ? { type: "function", function: { name: opts.forceTool } }
      : "auto";
  }
  return body;
}

export function parseToolQuery(rawArgs: string): string {
  try {
    const parsed = JSON.parse(rawArgs || "{}") as { query?: unknown };
    if (typeof parsed.query === "string") return parsed.query.trim();
  } catch {
    /* malformed */
  }
  return "";
}

export function hasVaultResults(messages: ConvoMessage[]): boolean {
  return messages.some((m) => m.role === "tool");
}

type FetchFn = typeof fetch;

async function callOpenAiCompat(
  route: OpenAiCompatRoute,
  messages: ConvoMessage[],
  fetchFn: FetchFn,
  forceTool?: string,
): Promise<{ content: string; tool_calls: ToolCall[] }> {
  const resp = await fetchFn(route.url, {
    method: "POST",
    headers: openAiHeaders(route),
    body: JSON.stringify(openAiBody(route, messages, { stream: false, tools: true, forceTool })),
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    const quota = route.isFreePool && (isQuotaStatus(resp.status) || parseUpstreamQuota(detail));
    throw new UpstreamError(`upstream ${resp.status}: ${detail.slice(0, 300)}`, quota);
  }
  const data = (await resp.json()) as {
    choices?: Array<{
      message?: { content?: string | null; tool_calls?: ToolCall[] };
    }>;
    error?: { message?: string };
  };
  if (data.error?.message) {
    throw new UpstreamError(data.error.message, route.isFreePool);
  }
  const msg = data.choices?.[0]?.message;
  return {
    content: msg?.content ?? "",
    tool_calls: msg?.tool_calls ?? [],
  };
}

type AnthropicBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string };

function toAnthropicMessages(convo: ConvoMessage[]): {
  system: string;
  messages: Array<{ role: "user" | "assistant"; content: string | AnthropicBlock[] }>;
} {
  const systemParts: string[] = [];
  const messages: Array<{ role: "user" | "assistant"; content: string | AnthropicBlock[] }> = [];

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
    if (m.role === "tool") {
      const last = messages[messages.length - 1];
      const block: AnthropicBlock = {
        type: "tool_result",
        tool_use_id: m.tool_call_id ?? "",
        content: m.content,
      };
      if (last?.role === "user" && Array.isArray(last.content)) {
        last.content.push(block);
      } else {
        messages.push({ role: "user", content: [block] });
      }
    }
  }

  return { system: systemParts.join("\n\n"), messages };
}

async function callAnthropic(
  route: AnthropicRoute,
  convo: ConvoMessage[],
  fetchFn: FetchFn,
): Promise<{ content: string; tool_calls: ToolCall[] }> {
  const { system, messages } = toAnthropicMessages(convo);
  const resp = await fetchFn("https://api.anthropic.com/v1/messages", {
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
  });
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    throw new UpstreamError(`anthropic ${resp.status}: ${detail.slice(0, 300)}`);
  }
  const data = (await resp.json()) as {
    content?: Array<{ type?: string; text?: string; id?: string; name?: string; input?: unknown }>;
    error?: { message?: string };
  };
  if (data.error?.message) throw new UpstreamError(data.error.message);
  let content = "";
  const tool_calls: ToolCall[] = [];
  for (const block of data.content ?? []) {
    if (block.type === "text" && typeof block.text === "string") content += block.text;
    if (block.type === "tool_use" && block.id && block.name) {
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

export async function callModel(
  route: LlmRoute,
  messages: ConvoMessage[],
  fetchFn: FetchFn,
  forceTool?: string,
): Promise<{ content: string; tool_calls: ToolCall[] }> {
  if (route.kind === "anthropic") {
    return callAnthropic(route, messages, fetchFn);
  }
  return callOpenAiCompat(route, messages, fetchFn, forceTool);
}
