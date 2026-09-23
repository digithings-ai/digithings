/**
 * Non-AI-SDK protocol mappers (#4543).
 *
 * Each mapper is fed a canned upstream stream and the resulting UI message
 * stream is inspected for the normalized chunks: reasoning, tool rows and
 * answer text must all surface, whatever the protocol. This is the parity
 * contract the backend matrix promises.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { createLangGraphStreamResponse } from "@/lib/adapters/langgraph/stream";
import { createAgUiStreamResponse } from "@/lib/adapters/ag-ui/stream";
import { createA2aStreamResponse } from "@/lib/adapters/a2a/stream";
import { createNonAiSdkStreamResponse } from "@/lib/adapters/non-ai-sdk";
import type { UIMessage } from "ai";

const USER_MESSAGE: UIMessage = {
  id: "u1",
  role: "user",
  parts: [{ type: "text", text: "hello" }],
};

const HEADERS = { "X-Test": "1" };

/** Stub global fetch with a canned SSE (or JSON) upstream response. */
function stubUpstream(body: string, contentType = "text/event-stream") {
  const fetchMock = vi.fn(
    async () =>
      new Response(body, { status: 200, headers: { "content-type": contentType } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The UI message stream as text — enough to assert the emitted chunks. */
async function bodyOf(res: Response): Promise<string> {
  return await res.text();
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("langgraph mapper (#4543)", () => {
  const CANNED = [
    'event: messages/partial\ndata: [{"type":"AIMessageChunk","content":"","additional_kwargs":{"reasoning_content":"let me think"}}]\n\n',
    'event: messages/partial\ndata: [{"type":"AIMessageChunk","content":"Hello ","tool_call_chunks":[{"id":"call_1","name":"search","args":"{\\"q\\":"}]}]\n\n',
    'event: messages/partial\ndata: [{"type":"AIMessageChunk","content":"world","tool_call_chunks":[{"id":"call_1","name":"","args":"\\"coffee\\"}"}]}]\n\n',
    'event: messages/partial\ndata: [{"type":"tool","tool_call_id":"call_1","content":"3 results"}]\n\n',
    'event: messages/partial\ndata: [{"type":"AIMessageChunk","content":"Done."}]\n\n',
  ].join("");

  it("normalizes reasoning, tool calls and text", async () => {
    const fetchMock = stubUpstream(CANNED);
    const res = await createLangGraphStreamResponse({
      backend: { type: "langgraph", apiUrl: "https://lg.example.com", assistantId: "agent" },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
      apiKey: null,
    });
    const body = await bodyOf(res);

    expect(body).toContain("let me think");
    expect(body).toContain('"reasoning-delta"');
    expect(body).toContain("Hello ");
    expect(body).toContain("world");
    expect(body).toContain("Done.");
    expect(body).toContain('"tool-input-start"');
    expect(body).toContain("search");
    expect(body).toContain("3 results");
    // The partial `tool_call_chunks` args are accumulated, so the completed row
    // carries the input even though no settled `tool_calls` frame arrived.
    expect(body).toContain("coffee");

    // Stateless run: the assistant id and the chat messages go upstream.
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://lg.example.com/runs/stream");
    const sent = JSON.parse(String(init.body)) as {
      assistant_id: string;
      input: { messages: Array<{ role: string; content: string }> };
    };
    expect(sent.assistant_id).toBe("agent");
    expect(sent.input.messages).toEqual([{ role: "user", content: "hello" }]);
  });

  it("reads a CRLF-delimited stream (the sse-starlette default)", async () => {
    stubUpstream(CANNED.replace(/\n/g, "\r\n"));
    const res = await createLangGraphStreamResponse({
      backend: { type: "langgraph", apiUrl: "https://lg.example.com", assistantId: "agent" },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
      apiKey: null,
    });
    const body = await bodyOf(res);
    expect(body).toContain("Hello ");
    expect(body).toContain("Done.");
    expect(body).toContain('"tool-input-start"');
  });

  it("sends the key from the named env var as x-api-key", async () => {
    vi.stubEnv("DIGICHAT_BACKEND_LG_KEY", "lg-secret");
    const fetchMock = stubUpstream(CANNED);
    await createNonAiSdkStreamResponse({
      backend: {
        type: "langgraph",
        apiUrl: "https://lg.example.com",
        assistantId: "agent",
        apiKeyEnv: "DIGICHAT_BACKEND_LG_KEY",
      },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
    });
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["x-api-key"]).toBe("lg-secret");
  });
});

describe("ag-ui mapper (#4543)", () => {
  const CANNED = [
    'data: {"type":"THINKING_TEXT_MESSAGE_CONTENT","delta":"thinking..."}\n\n',
    'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"Hi"}\n\n',
    'data: {"type":"TOOL_CALL_START","toolCallId":"t1","toolCallName":"lookup"}\n\n',
    'data: {"type":"TOOL_CALL_ARGS","toolCallId":"t1","delta":"{\\"x\\":1}"}\n\n',
    'data: {"type":"TOOL_CALL_RESULT","toolCallId":"t1","content":"ok"}\n\n',
    'data: {"type":"TEXT_MESSAGE_CONTENT","delta":" bye"}\n\n',
  ].join("");

  it("normalizes thinking, tool calls and text", async () => {
    const fetchMock = stubUpstream(CANNED);
    const res = await createAgUiStreamResponse({
      backend: { type: "ag-ui", url: "https://agui.example.com/run" },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
      apiKey: "agui-secret",
    });
    const body = await bodyOf(res);

    expect(body).toContain("thinking...");
    expect(body).toContain('"reasoning-delta"');
    expect(body).toContain("Hi");
    expect(body).toContain(" bye");
    expect(body).toContain("lookup");
    expect(body).toContain("ok");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://agui.example.com/run");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer agui-secret");
  });

  it("surfaces RUN_ERROR as a failed status row", async () => {
    stubUpstream('data: {"type":"RUN_ERROR","message":"boom"}\n\n');
    const res = await createAgUiStreamResponse({
      backend: { type: "ag-ui", url: "https://agui.example.com/run" },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
      apiKey: null,
    });
    const body = await bodyOf(res);
    expect(body).toContain("boom");
    expect(body).toContain('"data-status"');
    expect(body).toContain('"failed"');
  });
});

describe("a2a mapper (#4543)", () => {
  const CANNED = [
    'data: {"jsonrpc":"2.0","id":"1","result":{"kind":"status-update","status":{"state":"working"}}}\n\n',
    'data: {"jsonrpc":"2.0","id":"1","result":{"kind":"artifact-update","artifact":{"artifactId":"a1","parts":[{"kind":"text","text":"Part one."}]}}}\n\n',
    'data: {"jsonrpc":"2.0","id":"1","result":{"kind":"status-update","status":{"state":"completed"},"final":true}}\n\n',
  ].join("");

  it("normalizes artifact text and status", async () => {
    const fetchMock = stubUpstream(CANNED);
    const res = await createA2aStreamResponse({
      backend: { type: "a2a", baseUrl: "https://a2a.example.com" },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
      apiKey: null,
    });
    const body = await bodyOf(res);

    expect(body).toContain("Part one.");
    expect(body).toContain('"text-delta"');
    // A2A has no reasoning channel — nothing may claim otherwise.
    expect(body).not.toContain('"reasoning-delta"');

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://a2a.example.com");
    const sent = JSON.parse(String(init.body)) as { method: string };
    expect(sent.method).toBe("message/stream");
  });

  it("emits only the delta when an artifact update resends cumulative text", async () => {
    stubUpstream(
      [
        'data: {"jsonrpc":"2.0","id":"1","result":{"kind":"artifact-update","artifact":{"artifactId":"a1","parts":[{"kind":"text","text":"Part one."}]}}}\n\n',
        'data: {"jsonrpc":"2.0","id":"1","result":{"kind":"artifact-update","artifact":{"artifactId":"a1","parts":[{"kind":"text","text":"Part one. Part two."}]}}}\n\n',
      ].join(""),
    );
    const res = await createA2aStreamResponse({
      backend: { type: "a2a", baseUrl: "https://a2a.example.com" },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
      apiKey: null,
    });
    const body = await bodyOf(res);
    // The resend contributes only " Part two." — the shared prefix is not replayed.
    expect(body).toContain(" Part two.");
    expect(body.match(/Part one\./g)?.length).toBe(1);
  });

  it("handles a blocking JSON-RPC server that answers with one envelope", async () => {
    stubUpstream(
      JSON.stringify({
        jsonrpc: "2.0",
        id: "1",
        result: {
          kind: "task",
          status: { state: "completed" },
          artifacts: [{ artifactId: "a1", parts: [{ kind: "text", text: "Blocking answer." }] }],
        },
      }),
      "application/json",
    );
    const res = await createA2aStreamResponse({
      backend: { type: "a2a", baseUrl: "https://a2a.example.com" },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
      apiKey: null,
    });
    expect(await bodyOf(res)).toContain("Blocking answer.");
  });
});

describe("non-AI-SDK credential handling (#4543)", () => {
  it("answers 502 naming the env var and makes no upstream call", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await createNonAiSdkStreamResponse({
      backend: {
        type: "langgraph",
        apiUrl: "https://lg.example.com",
        assistantId: "agent",
        apiKeyEnv: "DIGICHAT_BACKEND_MISSING_KEY",
      },
      messages: [USER_MESSAGE],
      responseHeaders: HEADERS,
      activityDetail: "full",
    });
    expect(res.status).toBe(502);
    const payload = (await res.json()) as { error: string; message: string };
    expect(payload.error).toBe("backend_unavailable");
    expect(payload.message).toContain("DIGICHAT_BACKEND_MISSING_KEY");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
