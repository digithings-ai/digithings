import { it, expect, vi, afterEach } from "vitest";
import type { UIMessage } from "ai";
import {
  DIGIGRAPH_UNAVAILABLE_MESSAGE,
  RATE_LIMIT_RETRY_CODE,
  UPSTREAM_BOOT_MAX_ATTEMPTS,
  UPSTREAM_BOOT_MAX_ELAPSED_MS,
  UPSTREAM_BOOT_RETRY_CODE,
  createDigigraphTraceStreamResponse,
  digigraphErrorToEmbedPayload,
  isUpstreamBootRetry,
  parseRetryAfterMs,
  rateLimitRetryPayload,
  retryAfterSeconds,
} from "./stream";
import {
  BYOK_MODEL_REMEDIABLE_MESSAGE,
  formatEmbedChatError,
  parseEmbedChatError,
  shouldSuggestByokOnEmbedError,
} from "@/lib/embed-chat-error";

afterEach(() => vi.restoreAllMocks());

const userMessage = (text: string) =>
  ({ id: "u1", role: "user", parts: [{ type: "text", text }] }) as UIMessage;

// A 500 body from digigraph can carry stack traces, internal hostnames, and
// prompt echoes. Streaming it verbatim to an anonymous embed visitor publishes
// all of that; the detail belongs in the server log.
it("does not stream the upstream error body to the browser", async () => {
  const secret = "Traceback: psycopg2 connect to db.internal:5432 failed";
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(secret, { status: 500, statusText: "Internal Server Error" })
  );
  const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();

  expect(res.headers.get("x-vercel-ai-ui-message-stream")).toBe("v1");
  expect(body).not.toContain(secret);
  expect(body).not.toContain("db.internal");
  // #3910: a failed turn must be a real stream error the runtime can render,
  // never a success-looking assistant text bubble.
  expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  expect(body).not.toContain('"type":"text-delta"');
  expect(body).not.toContain('"type":"text-start"');
  expect(errorLog).toHaveBeenCalled();
});

// #3910: a real 200 always carries a non-null body even when the upstream sends
// zero bytes, so `!res.body` only catches 204/205/HEAD. An SSE stream that ends
// with no events must still fail the turn — otherwise it completes as a silent
// empty reply with no error state and no Retry.
it("surfaces a 200 SSE stream with no events as a stream error", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("", { status: 200, headers: { "content-type": "text/event-stream" } })
  );
  const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  expect(body).not.toContain('"type":"text-delta"');
  expect(errorLog).toHaveBeenCalled();
});

it("surfaces a [DONE]-only 200 SSE stream as a stream error", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("data: [DONE]\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    })
  );
  const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  expect(body).not.toContain('"type":"text-delta"');
  expect(errorLog).toHaveBeenCalled();
});

// The emptiness check must not fire on a real answer: a streamed text delta is
// the normal success shape.
it("still streams a genuinely non-empty 200 SSE reply", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({ choices: [{ delta: { content: "Hello." } }] })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();

  expect(errorTextFrom(body)).toBeUndefined();
  expect(body).toContain('"type":"text-delta"');
  expect(body).toContain("Hello.");
});

// #3978: digigraph appends the run's provider-reported usage as a final SSE chunk
// with a top-level `usage` object. The adapter forwards it as message metadata,
// which the runtime folds into `metadata.custom.usage` — never fabricated when the
// upstream reports none.
it("forwards the provider-reported SSE usage chunk as message metadata", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({ choices: [{ delta: { content: "Hi" } }] })}\n\n`,
        `data: ${JSON.stringify({
          choices: [{ delta: {} }],
          usage: { prompt_tokens: 11, completion_tokens: 4, total_tokens: 15 },
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  expect(eventsFrom(body)).toContainEqual({
    type: "message-metadata",
    messageMetadata: {
      usage: { inputTokens: 11, outputTokens: 4, totalTokens: 15 },
    },
  });
});

it("omits usage metadata when the upstream stream reports no usage", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({ choices: [{ delta: { content: "Hi" } }] })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  expect(eventsFrom(body).some((event) => event.type === "message-metadata")).toBe(false);
});

// A reply that streams only a tool/activity part and no answer text is not
// empty — it must not be rewritten as "the assistant is unavailable".
it("does not misclassify an activity-only 200 stream as empty", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "tool_call",
                  payload: {
                    tool: "digisearch",
                    query: "what is digigraph",
                    status: "started",
                  },
                },
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();

  expect(errorTextFrom(body)).toBeUndefined();
  expect(body).not.toContain('"type":"text-delta"');
  expect(body).toContain('"type":"tool-input-start"');
});

// #3910: fetchGuarded refuses to carry the BYOK/Authorization headers across a
// cross-origin redirect (#2572). That refusal is an infrastructure failure and
// must surface as an error the visitor can retry, not as a fake reply.
it("surfaces a cross-origin credential redirect as a stream error", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(null, {
      status: 302,
      headers: { location: "https://evil.example.com/steal" },
    })
  );
  const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: { Authorization: "Bearer from-upstream-headers" },
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  expect(body).not.toContain('"type":"text-delta"');
  expect(body).not.toContain("evil.example.com");
  expect(errorLog).toHaveBeenCalled();
});

// The authenticated path emits standard tool / data-status / source parts (2.0).
it("never emits data-digigraphTrace on the authenticated path", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "external_activity",
                  payload: { label: "Searching…", status: "in_progress" },
                  workflow_id: "wf-1",
                },
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();

  expect(body).not.toContain('"type":"data-digigraphTrace"');
  expect(body).not.toContain('"type":"data-digichatActivity"');
  expect(body).toContain('"type":"data-status"');
  expect(body).toContain("Searching…");
  expect(body).not.toContain('"workflow_id"');
});

it("maps reasoning_content deltas onto reasoning UI chunks", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [{ delta: { reasoning_content: "internal chain of thought" } }],
        })}\n\n`,
        `data: ${JSON.stringify({
          choices: [{ delta: { content: "Final answer." } }],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();
  expect(body).toContain('"type":"reasoning-start"');
  expect(body).toContain('"type":"reasoning-delta"');
  expect(body).toContain("internal chain of thought");
  expect(body).toContain("Final answer.");
});

it("mints a new reasoning id after a tool round on the dogfood stream", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [{ delta: { reasoning_content: "look in vault" } }],
        })}\n\n`,
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "tool_call",
                  payload: { tool: "digivault_get_note", status: "started" },
                },
              },
            },
          ],
        })}\n\n`,
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "digivault_get_note",
                  payload: {
                    toolName: "digivault_get_note",
                    vault_paths: ["clients/digithings/a.md"],
                    hits: [
                      {
                        body: "# note",
                        metadata: { vault_path: "clients/digithings/a.md" },
                      },
                    ],
                  },
                },
              },
            },
          ],
        })}\n\n`,
        `data: ${JSON.stringify({
          choices: [{ delta: { reasoning_content: "now I can answer" } }],
        })}\n\n`,
        `data: ${JSON.stringify({
          choices: [{ delta: { content: "Here is the note." } }],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } },
    ),
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("load the note")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();
  const events = body
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("data: ") && l !== "data: [DONE]")
    .map((l) => JSON.parse(l.slice(6)) as Record<string, unknown>);
  const starts = events.filter((e) => e.type === "reasoning-start");
  expect(starts).toHaveLength(2);
  expect(starts[0]?.id).not.toBe(starts[1]?.id);
  const types = events.map((e) => e.type);
  expect(types.indexOf("reasoning-end")).toBeLessThan(types.indexOf("tool-input-start"));
  expect(types.lastIndexOf("reasoning-start")).toBeGreaterThan(types.indexOf("tool-input-start"));
  const toolStart = events.find((e) => e.type === "tool-input-start");
  expect(toolStart).toMatchObject({
    toolName: "digivault_get_note",
    title: "digivault_get_note",
  });
  expect(body).not.toContain("digivault get note");
});

it("posts the full multi-turn history to digigraph chat completions", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("data: [DONE]\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    })
  );

  const messages = [
    { id: "1", role: "user", parts: [{ type: "text", text: "first" }] },
    { id: "2", role: "assistant", parts: [{ type: "text", text: "reply" }] },
    { id: "3", role: "user", parts: [{ type: "text", text: "second" }] },
  ] as UIMessage[];

  await createDigigraphTraceStreamResponse({
    messages,
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });

  expect(fetchSpy).toHaveBeenCalled();
  const init = fetchSpy.mock.calls[0]?.[1] as { body?: string };
  const payload = JSON.parse(init.body ?? "{}") as {
    messages?: Array<{ role: string; content: string }>;
  };
  expect(payload.messages).toHaveLength(3);
  expect(payload.messages?.map((m) => m.content)).toEqual(["first", "reply", "second"]);
});

it("forwards a regenerate-shaped transcript without the dropped assistant turn", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("data: [DONE]\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    }),
  );

  // Client already truncated: last assistant dropped; ends on the user turn being re-answered.
  const messages = [
    { id: "1", role: "user", parts: [{ type: "text", text: "first" }] },
    { id: "2", role: "assistant", parts: [{ type: "text", text: "old reply" }] },
    { id: "3", role: "user", parts: [{ type: "text", text: "ask again" }] },
  ] as UIMessage[];

  await createDigigraphTraceStreamResponse({
    messages: messages.slice(0, 3), // ends on user — no trailing assistant
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });

  const init = fetchSpy.mock.calls[0]?.[1] as { body?: string; signal?: AbortSignal };
  const payload = JSON.parse(init.body ?? "{}") as {
    messages?: Array<{ role: string; content: string }>;
  };
  expect(payload.messages?.map((m) => m.content)).toEqual(["first", "old reply", "ask again"]);
  expect(payload.messages?.at(-1)?.role).toBe("user");
});

it("passes AbortSignal through to digigraph fetch (Stop)", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("data: [DONE]\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    }),
  );
  const controller = new AbortController();
  await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
    signal: controller.signal,
  });
  const init = fetchSpy.mock.calls[0]?.[1] as { signal?: AbortSignal };
  expect(init.signal).toBe(controller.signal);
});

// On the embed path with activityDetail: "off", neither the legacy part nor
// the gated activity span should be emitted — this prevents disclosure of
// internal payload fields like workflow_id to anonymous visitors.
it("suppresses both parts on the embed path with activityDetail off", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "external_activity",
                  payload: { label: "Searching…", status: "in_progress" },
                  workflow_id: "wf-internal-1",
                  request_id: "req-internal-1",
                },
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  // Neither part present on embed path with activityDetail: off.
  expect(body).not.toContain('"type":"data-digigraphTrace"');
  expect(body).not.toContain('"type":"data-digichatActivity"');
  // Regression test: internal payload fields must not leak.
  expect(body).not.toContain("wf-internal-1");
  expect(body).not.toContain("req-internal-1");
  expect(body).not.toContain('"workflow_id"');
  expect(body).not.toContain('"request_id"');
});

// On the embed path with activityDetail: "full", the activity span should be
// emitted (gated), but the legacy part must NOT be emitted — it is
// authenticated-path-only.
it("emits the activity span but not the legacy part on the embed path with activityDetail full", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "external_activity",
                  payload: { label: "Searching…", status: "in_progress" },
                  workflow_id: "wf-1",
                },
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();

  // Activity span present on embed path with activityDetail: full.
  expect(body).toContain('"type":"data-status"');
  expect(body).toContain("Searching…");
  expect(body).not.toContain('"type":"data-digichatActivity"');
  // But legacy part is NOT emitted on embed path.
  expect(body).not.toContain('"type":"data-digigraphTrace"');
  expect(body).not.toContain('"workflow_id"');
});

it("emits rich retrieve activity for rag_sources on the gated path", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "rag_sources",
                  payload: {
                    sources: [
                      {
                        source_id: "doc-1",
                        snippet: "hello",
                        metadata: { title: "Auth", evidence_tier: "tier_a", publication_year: 2023 },
                      },
                    ],
                  },
                },
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();
  expect(body).toContain('"type":"tool-output-available"');
  expect(body).toContain('"tier":"tier_a"');
  expect(body).toContain('"year":2023');
  expect(body).not.toContain('"type":"data-digichatActivity"');
  expect(body).not.toContain('"type":"data-digigraphTrace"');
});

it("maps digigraph_error code to embed-chat-error payload", () => {
  const payload = digigraphErrorToEmbedPayload({
    code: "free_quota_exceeded",
    message: "Free-tier model quota is exhausted.",
  });
  expect(JSON.parse(payload)).toEqual({
    error: "free_quota_exceeded",
    message: "Free-tier model quota is exhausted.",
  });
});

it("relays llm_error detail for the embed disclosure", () => {
  const payload = digigraphErrorToEmbedPayload({
    code: "llm_error",
    message: "No endpoints found for this model.",
    detail: "Error code: 404",
  });
  expect(JSON.parse(payload)).toEqual({
    error: "llm_error",
    message: "No endpoints found for this model.",
    detail: "Error code: 404",
  });
});

it("drops upstream message for BYOK remediable digigraph_error codes", () => {
  const sensitive = "Provider openai is not supported for your X-BYOK-Provider header.";
  const payload = digigraphErrorToEmbedPayload({
    code: "byok_default_model_provider_mismatch",
    message: sensitive,
  });
  expect(JSON.parse(payload)).toEqual({ error: "byok_default_model_provider_mismatch" });
  expect(payload).not.toContain("openai");
});

it("relays free_quota_exceeded message on the SSE digigraph_error path", async () => {
  const quotaMessage =
    "Free-tier model quota is exhausted. Add your own API key (BYOK) to continue.";
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_error: {
                  code: "free_quota_exceeded",
                  message: quotaMessage,
                },
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } },
    ),
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  expect(body).toContain("free_quota_exceeded");
  expect(body).toContain(quotaMessage);
  const errorChunk = body
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice(6))
    .find((raw) => raw.includes("free_quota_exceeded"));
  expect(errorChunk).toBeTruthy();
  const parsed = JSON.parse(errorChunk!) as { type?: string; errorText?: string };
  expect(parsed.type).toBe("error");
  const embedErr = parseEmbedChatError(new Error(parsed.errorText));
  expect(embedErr?.code).toBe("free_quota_exceeded");
  expect(
    shouldSuggestByokOnEmbedError({
      llmAccess: "free_then_byok",
      gateMode: "ungated",
      errorCode: embedErr?.code,
    }),
  ).toBe(true);
});

it("surfaces delta.digigraph_error as a stream error for BYOK handoff", async () => {
  const sensitive =
    "Provider openai is not supported for your X-BYOK-Provider header.";
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_error: {
                  code: "byok_default_model_provider_mismatch",
                  message: sensitive,
                },
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } },
    ),
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  expect(body).toContain("byok_default_model_provider_mismatch");
  expect(body).not.toContain("openai");
  const errorText = errorTextFrom(body);
  expect(errorText).toBeTruthy();
  expect(JSON.parse(errorText!)).toEqual({
    error: "byok_default_model_provider_mismatch",
  });
});

it("settles the reasoning part when the turn errors mid-stream", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({ choices: [{ delta: { reasoning_content: "Checking the corpus" } }] })}\n\n`,
        `data: ${JSON.stringify({ choices: [{ delta: { digigraph_error: { code: "upstream_error", message: "boom" } } }] })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } },
    ),
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  const body = await new Response(res.body).text();

  expect(body).toContain("upstream_error");
  const reasoningEnd = body.indexOf("reasoning-end");
  const errorIndex = body.indexOf('"errorText"');
  expect(reasoningEnd).toBeGreaterThan(-1);
  expect(errorIndex).toBeGreaterThan(-1);
  expect(reasoningEnd).toBeLessThan(errorIndex);
});

it("strips Open WebUI tool dumps from streamed answer text", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                content:
                  "<details><summary>Tool</summary>dump</details>\n\nClean answer.",
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } },
    ),
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();
  expect(body).toContain("Clean answer.");
  expect(body).not.toContain("<details>");
});

// #2306 follow-up: narration written alongside a round's tool calls (e.g. "I will
// load the full notes now.") must not concatenate with the final answer in the
// same visible text part. Confirmed live in production before this fix: the two
// read as one continuous, self-contradicting block.
it("splits narration from the final answer into separate text parts on round_boundary", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({ choices: [{ delta: { content: "I will load the notes." } }] })}\n\n`,
        `data: ${JSON.stringify({
          choices: [
            { delta: { digigraph_trace: { v: 1, type: "round_boundary", payload: { round_idx: 0 } } } },
          ],
        })}\n\n`,
        `data: ${JSON.stringify({ choices: [{ delta: { content: "Here is the real answer." } }] })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();
  const events = body
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("data: ") && l !== "data: [DONE]")
    .map((l) => JSON.parse(l.slice(6)) as Record<string, unknown>);

  const textStarts = events.filter((e) => e.type === "text-start");
  const textEnds = events.filter((e) => e.type === "text-end");
  // Two distinct text parts: the narration, and the real answer.
  expect(textStarts).toHaveLength(2);
  expect(textEnds).toHaveLength(2);
  const [firstId, secondId] = textStarts.map((e) => e.id);
  expect(firstId).not.toBe(secondId);

  const deltasFor = (id: unknown) =>
    events
      .filter((e) => e.type === "text-delta" && e.id === id)
      .map((e) => e.delta)
      .join("");
  expect(deltasFor(firstId)).toBe("I will load the notes.");
  expect(deltasFor(secondId)).toBe("Here is the real answer.");

  // The round_boundary trace itself must render no visible activity chip.
  expect(body).not.toContain("round_boundary");
});

// A normal single-round exchange (no tool calls at all) must be completely
// unaffected: exactly one text part, same as before this change.
it("keeps a single unbroken text part when no round_boundary ever fires", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({ choices: [{ delta: { content: "Hello " } }] })}\n\n`,
        `data: ${JSON.stringify({ choices: [{ delta: { content: "there." } }] })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();
  const events = body
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("data: ") && l !== "data: [DONE]")
    .map((l) => JSON.parse(l.slice(6)) as Record<string, unknown>);

  expect(events.filter((e) => e.type === "text-start")).toHaveLength(1);
  expect(events.filter((e) => e.type === "text-end")).toHaveLength(1);
  expect(events.filter((e) => e.type === "text-start")[0]?.id).toBe("assistant-main");
});

it("emits tool parts before the answer text when tools complete first", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "tool_call",
                  payload: { tool: "digisearch", query: "what is digigraph", status: "started" },
                },
              },
            },
          ],
        })}\n\n`,
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "rag_sources",
                  payload: {
                    tool: "digisearch",
                    query: "what is digigraph",
                    sources: [
                      {
                        snippet: "# digigraph",
                        metadata: { source_url: "repo://digithings/digigraph/ARCHITECTURE.md" },
                      },
                    ],
                    hit_count: 1,
                  },
                },
              },
            },
          ],
        })}\n\n`,
        `data: ${JSON.stringify({ choices: [{ delta: { content: "digigraph is the hub." } }] })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } },
    ),
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("What is digigraph?")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();
  const events = body
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("data: ") && l !== "data: [DONE]")
    .map((l) => JSON.parse(l.slice(6)) as Record<string, unknown>);

  const types = events.map((e) => e.type);
  const toolStartAt = types.indexOf("tool-input-start");
  const textStartAt = types.indexOf("text-start");
  expect(toolStartAt).toBeGreaterThanOrEqual(0);
  expect(textStartAt).toBeGreaterThan(toolStartAt);

  const input = events.find((e) => e.type === "tool-input-available");
  expect(input?.input).toEqual({ query: "what is digigraph" });
  const output = events.find((e) => e.type === "tool-output-available");
  expect(output?.output).toMatchObject({
    query: "what is digigraph",
    hitCount: 1,
  });
  expect(Array.isArray((output?.output as { documents?: unknown[] })?.documents)).toBe(true);
});

it("opts digigraph out of Open WebUI format on the dogfood stream path", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("data: [DONE]\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    })
  );

  await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
  });

  expect(fetchSpy).toHaveBeenCalled();
  const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
  const headers = new Headers(init.headers);
  expect(headers.get("X-Suppress-Tool-Stream")).toBe("1");
  expect(headers.get("X-Response-Format")).toBe("plain");
});

// `upstreamHeaders` is the only thing that decides which key digigraph bills, so
// pin it. Every other fixture here passes `upstreamHeaders: {}`, which is not what
// route.ts sends: it always builds the Authorization entry itself. This asserts the
// production shape -- and it is why the adapter carries no Authorization line of its
// own to be overridden.
it("sends the Authorization supplied in upstreamHeaders", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("data: [DONE]\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    })
  );

  await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: { Authorization: "Bearer from-upstream-headers" },
    responseHeaders: {},
    activityDetail: "full",
  });

  const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
  expect(new Headers(init.headers).get("Authorization")).toBe("Bearer from-upstream-headers");
});

const eventsFrom = (body: string): Array<Record<string, unknown>> =>
  body
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice(6))
    .map((raw) => {
      try {
        return JSON.parse(raw) as Record<string, unknown>;
      } catch {
        return null;
      }
    })
    .filter((chunk): chunk is Record<string, unknown> => chunk !== null);

const errorTextFrom = (body: string): string | undefined =>
  body
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice(6))
    .map((raw) => {
      try {
        return JSON.parse(raw) as { type?: string; errorText?: string };
      } catch {
        return null;
      }
    })
    .find((chunk) => chunk?.type === "error")?.errorText;

const streamFor400 = async (upstreamBody: string) => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(upstreamBody, { status: 400, statusText: "Bad Request" }),
  );
  const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});
  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  return { body: await new Response(res.body).text(), errorLog };
};

// A BYOK key bound with no model is refused by digigraph with a 400 whose code
// the frontend already knows how to act on. Swallowing it left the visitor at
// "the assistant is unavailable" with nothing to do (#2515).
it("relays an allowlisted BYOK refusal code out of a 400 body", async () => {
  // digibase's json_error_response nests the code under `error`.
  const { body } = await streamFor400(
    JSON.stringify({
      error: {
        code: "byok_default_model_provider_mismatch",
        message: "This deployment's default model is served by openrouter, not openai.",
        request_id: "req-1",
        service: "digigraph",
      },
    }),
  );

  expect(body).toContain("byok_default_model_provider_mismatch");
  const errorText = errorTextFrom(body);
  const parsed = parseEmbedChatError(new Error(errorText));
  expect(parsed?.code).toBe("byok_default_model_provider_mismatch");
  expect(formatEmbedChatError(new Error(errorText))).toBe(BYOK_MODEL_REMEDIABLE_MESSAGE);
  expect(
    shouldSuggestByokOnEmbedError({
      // free_then_byok deliberately, not byok_only: the byok_only/operator branch
      // (embed-chat-error.ts:151) returns true for *any* non-empty code, so naming it
      // here would describe a path that ignores the allowlist entirely. free_then_byok
      // is the branch that consults it (:148) and the policy digithings.ai actually
      // runs. Note what this line does NOT do: it expects true, so it cannot catch the
      // allowlist being *loosened* — dropping the code is caught above, by the relay
      // itself refusing and `body` no longer containing it.
      llmAccess: "free_then_byok",
      showByok: true,
      errorCode: parsed?.code,
    }),
  ).toBe(true);
});

it("relays byok_model_provider_mismatch out of a nested 400 body (#2524)", async () => {
  const { body } = await streamFor400(
    JSON.stringify({
      error: {
        code: "byok_model_provider_mismatch",
        message: "Model openai/gpt-4o-mini does not match provider openai.",
        request_id: "req-3",
        service: "digigraph",
      },
    }),
  );

  expect(body).toContain("byok_model_provider_mismatch");
  const errorText = errorTextFrom(body);
  const parsed = parseEmbedChatError(new Error(errorText));
  expect(parsed?.code).toBe("byok_model_provider_mismatch");
  expect(formatEmbedChatError(new Error(errorText!))).toBe(BYOK_MODEL_REMEDIABLE_MESSAGE);
});

// Only the code crosses the boundary. digigraph's message for this refusal
// f-strings the caller's own X-BYOK-Provider header into its text, and a 400
// body carries a request_id and service name besides.
it("relays the code without any of the upstream body", async () => {
  const { body } = await streamFor400(
    JSON.stringify({
      error: {
        code: "byok_model_required",
        message: "openrouter requires an explicit model at db.internal:5432",
        request_id: "req-2",
        service: "digigraph",
      },
    }),
  );

  expect(body).toContain("byok_model_required");
  expect(body).not.toContain("db.internal");
  expect(body).not.toContain("req-2");
  expect(body).not.toContain("requires an explicit model");
  expect(body).not.toContain('"service"');
});

// A flat {code} body is accepted too — not every handler goes through digibase.
it("accepts a flat error envelope", async () => {
  const { body } = await streamFor400(JSON.stringify({ code: "byok_model_required" }));
  expect(errorTextFrom(body)).toContain("byok_model_required");
});

// The allowlist is the point: a code with no frontend copy would render as raw
// JSON, which is worse than the generic message. The body is still swallowed,
// but the turn must fail loudly (#3910).
it("surfaces a non-allowlisted upstream code as a stream error without leaking the body", async () => {
  const { body, errorLog } = await streamFor400(
    JSON.stringify({
      error: { code: "thread_error", message: "Traceback: connect to db.internal:5432" },
    }),
  );

  expect(body).not.toContain("thread_error");
  expect(body).not.toContain("db.internal");
  expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  expect(body).not.toContain('"type":"text-delta"');
  expect(errorLog).toHaveBeenCalled();
});

it("surfaces a non-JSON upstream body as a stream error without leaking the body", async () => {
  const { body } = await streamFor400("<html>502 Bad Gateway from nginx/1.25</html>");
  expect(body).not.toContain("nginx");
  expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  expect(body).not.toContain('"type":"text-delta"');
});

const streamFor429 = async (upstreamBody: string, retryAfter: string | null) => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(upstreamBody, {
      status: 429,
      statusText: "Too Many Requests",
      headers: retryAfter === null ? {} : { "retry-after": retryAfter },
    }),
  );
  const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});
  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "off",
  });
  return { body: await new Response(res.body).text(), errorLog };
};

// #4777: a digigraph 429 is rate-limited, not down — the turn must say when to
// retry instead of falling through to the generic unavailable-message.
it("surfaces a digigraph 429 as retry-in-N-seconds from Retry-After", async () => {
  const { body, errorLog } = await streamFor429(
    JSON.stringify({
      error: {
        code: "rate_limit_exceeded",
        message: "Rate limit exceeded for 203.0.113.7 on db.internal:5432",
        request_id: "req-429",
        service: "digigraph",
      },
    }),
    "60",
  );

  expect(errorTextFrom(body)).toContain(RATE_LIMIT_RETRY_CODE);
  const errorText = errorTextFrom(body)!;
  const parsed = parseEmbedChatError(new Error(errorText));
  expect(parsed?.code).toBe(RATE_LIMIT_RETRY_CODE);
  expect(formatEmbedChatError(new Error(errorText))).toBe(
    "Rate limit reached, retry in 60 seconds.",
  );
  // The relayed code keeps the rate-limit BYOK policy: free_then_byok tenants
  // open the sequence instead of dead-ending on the 429.
  expect(
    shouldSuggestByokOnEmbedError({
      llmAccess: "free_then_byok",
      showByok: true,
      gateMode: "ungated",
      errorCode: parsed?.code,
    }),
  ).toBe(true);
  // Server-composed copy only: no upstream text crosses to the visitor.
  expect(body).not.toContain("203.0.113.7");
  expect(body).not.toContain("db.internal");
  expect(body).not.toContain("req-429");
  expect(body).not.toContain("Rate limit exceeded for");
  expect(body).not.toContain(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  expect(body).not.toContain('"type":"text-delta"');
  expect(errorLog).toHaveBeenCalled();
});

// Status-gated, never body-parsed: a bare proxy 429 with no usable body or
// header still renders retry copy, not UNAVAILABLE.
it("falls back to copy without a number when Retry-After is absent", async () => {
  const { body } = await streamFor429("", null);

  const errorText = errorTextFrom(body)!;
  expect(formatEmbedChatError(new Error(errorText))).toBe(
    "Rate limit reached, please try again shortly.",
  );
  const parsed = parseEmbedChatError(new Error(errorText));
  expect(parsed?.code).toBe(RATE_LIMIT_RETRY_CODE);
  expect(body).not.toContain(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  expect(body).not.toContain('"type":"text-delta"');
});

it("parses Retry-After for display unclamped, rejects garbage", () => {
  expect(retryAfterSeconds("60")).toBe(60);
  expect(retryAfterSeconds("3600")).toBe(3600);
  expect(retryAfterSeconds(null)).toBeNull();
  expect(retryAfterSeconds("")).toBeNull();
  expect(retryAfterSeconds("soon")).toBeNull();
  expect(retryAfterSeconds("0")).toBeNull();
  expect(retryAfterSeconds("-5")).toBeNull();
  // HTTP-date has 1s resolution, so assert a window, not an exact delta.
  const httpDate = retryAfterSeconds(new Date(Date.now() + 90000).toUTCString());
  expect(httpDate).toBeGreaterThan(80000 / 1000);
  expect(httpDate).toBeLessThanOrEqual(90);
  expect(retryAfterSeconds(new Date(Date.now() - 7000).toUTCString())).toBeNull();
});

it("builds the relayed 429 payload with singular and fallback copy", () => {
  expect(JSON.parse(rateLimitRetryPayload("1"))).toEqual({
    error: RATE_LIMIT_RETRY_CODE,
    message: "Rate limit reached, retry in 1 second.",
  });
  expect(JSON.parse(rateLimitRetryPayload(null))).toEqual({
    error: RATE_LIMIT_RETRY_CODE,
    message: "Rate limit reached, please try again shortly.",
  });
});

// #4323: a sleeping stack container answers 503 while it boots. The turn must
// survive the cold start: report "connecting", retry upstream, then continue.
it("retries a 503 cold start and reports the connection status", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("stack container not ready", { status: 503 }))
      .mockResolvedValueOnce(
        new Response('data: {"choices":[{"delta":{"content":"Hello."}}]}\n\ndata: [DONE]\n\n', {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
      );

    const pendingBody = (async () => {
      const res = await createDigigraphTraceStreamResponse({
        messages: [userMessage("hi")],
        digigraphBaseUrl: "https://digigraph.internal",
        upstreamHeaders: {},
        responseHeaders: {},
        activityDetail: "full",
      });
      return new Response(res.body).text();
    })();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(eventsFrom(body)[0]).toEqual({
      type: "data-connection",
      id: "digigraph-connection",
      data: { state: "connecting" },
    });
    expect(eventsFrom(body).filter((event) => event.type === "data-connection")).toEqual([
      { type: "data-connection", id: "digigraph-connection", data: { state: "connecting" } },
      { type: "data-connection", id: "digigraph-connection", data: { state: "connected" } },
    ]);
    expect(errorTextFrom(body)).toBeUndefined();
    expect(body).toContain("Hello.");
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  } finally {
    vi.useRealTimers();
  }
});

it("keeps the unavailable error when the upstream stays cold after retries", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => new Response("stack container not ready", { status: 503 }));
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = (async () => {
      const res = await createDigigraphTraceStreamResponse({
        messages: [userMessage("hi")],
        digigraphBaseUrl: "https://digigraph.internal",
        upstreamHeaders: {},
        responseHeaders: {},
        activityDetail: "full",
      });
      return new Response(res.body).text();
    })();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
    expect(body).not.toContain('"type":"text-delta"');
    expect(fetchSpy).toHaveBeenCalledTimes(4);
    expect(errorLog).toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});

it("stops the retry when the request is aborted during a cold-start wait", async () => {
  vi.useFakeTimers();
  try {
    const controller = new AbortController();
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("stack container not ready", { status: 503 }));
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = (async () => {
      const res = await createDigigraphTraceStreamResponse({
        messages: [userMessage("hi")],
        digigraphBaseUrl: "https://digigraph.internal",
        upstreamHeaders: {},
        responseHeaders: {},
        activityDetail: "full",
        signal: controller.signal,
      });
      return new Response(res.body).text();
    })();
    await vi.advanceTimersByTimeAsync(100);
    controller.abort();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(errorTextFrom(body)).toBeTruthy();
  } finally {
    vi.useRealTimers();
  }
});

// #4753: boot-coded 503s (stack container_booting + Retry-After) get the
// extended budget; everything below pins that contract.

const boot503 = (retryAfter = "5", body?: string) =>
  new Response(
    body ?? JSON.stringify({ code: "container_booting", message: "stack container not ready" }),
    { status: 503, headers: { "retry-after": retryAfter } },
  );

const sseHello = () =>
  new Response('data: {"choices":[{"delta":{"content":"Hello."}}]}\n\ndata: [DONE]\n\n', {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });

const streamBody = async (init?: RequestInit & { signal?: AbortSignal }) => {
  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    activityDetail: "full",
    signal: init?.signal,
  });
  return new Response(res.body).text();
};

it("detects the boot code in flat, nested, and string envelopes only", () => {
  expect(isUpstreamBootRetry(JSON.stringify({ code: UPSTREAM_BOOT_RETRY_CODE }))).toBe(true);
  expect(
    isUpstreamBootRetry(JSON.stringify({ error: { code: UPSTREAM_BOOT_RETRY_CODE } })),
  ).toBe(true);
  expect(isUpstreamBootRetry(JSON.stringify({ error: UPSTREAM_BOOT_RETRY_CODE }))).toBe(true);
  expect(isUpstreamBootRetry("stack container not ready: timeout")).toBe(false);
  expect(isUpstreamBootRetry(JSON.stringify({ code: "overloaded" }))).toBe(false);
  expect(isUpstreamBootRetry(JSON.stringify({ error: { code: "overloaded" } }))).toBe(false);
  expect(isUpstreamBootRetry("")).toBe(false);
  expect(isUpstreamBootRetry("not json {")).toBe(false);
});

it("parses Retry-After seconds, clamps floods and hangs, rejects garbage", () => {
  expect(parseRetryAfterMs("5")).toBe(5000);
  expect(parseRetryAfterMs("0")).toBe(1000);
  expect(parseRetryAfterMs("3600")).toBe(30000);
  expect(parseRetryAfterMs(null)).toBeNull();
  expect(parseRetryAfterMs("")).toBeNull();
  expect(parseRetryAfterMs("soon")).toBeNull();
  // HTTP-date has 1s resolution, so assert a window, not an exact delta.
  const httpDate = parseRetryAfterMs(new Date(Date.now() + 7000).toUTCString());
  expect(httpDate).toBeGreaterThan(5000);
  expect(httpDate).toBeLessThanOrEqual(7000);
  expect(parseRetryAfterMs(new Date(Date.now() - 7000).toUTCString())).toBe(1000);
});

it("retries a boot-coded 503 and reports warming_up between connecting and connected", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(boot503())
      .mockResolvedValueOnce(sseHello());
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(eventsFrom(body).filter((event) => event.type === "data-connection")).toEqual([
      { type: "data-connection", id: "digigraph-connection", data: { state: "connecting" } },
      { type: "data-connection", id: "digigraph-connection", data: { state: "warming_up" } },
      { type: "data-connection", id: "digigraph-connection", data: { state: "connected" } },
    ]);
    expect(errorTextFrom(body)).toBeUndefined();
    expect(body).toContain("Hello.");
  } finally {
    vi.useRealTimers();
  }
});

it("accepts the boot code in the nested digibase envelope", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        boot503("5", JSON.stringify({ error: { code: UPSTREAM_BOOT_RETRY_CODE } })),
      )
      .mockResolvedValueOnce(sseHello());
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(body).toContain("warming_up");
    expect(body).toContain("Hello.");
    expect(errorTextFrom(body)).toBeUndefined();
  } finally {
    vi.useRealTimers();
  }
});

// Acceptance: a full ~240s boot (48 x Retry-After 5s) ends in a streamed
// answer with the warming state throughout — never the unavailable-message.
it("survives a simulated ~240s boot and streams the first send", async () => {
  vi.useFakeTimers();
  try {
    const boots = Array.from({ length: 48 }, () => boot503("5"));
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => boots.shift() ?? sseHello());
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(fetchSpy).toHaveBeenCalledTimes(49);
    expect(body).toContain("warming_up");
    expect(body).toContain("Hello.");
    expect(errorTextFrom(body)).toBeUndefined();
    expect(body).not.toContain(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  } finally {
    vi.useRealTimers();
  }
});

it("honors the server Retry-After exactly on the boot code", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(boot503("10"))
      .mockResolvedValueOnce(boot503("10"))
      .mockResolvedValue(sseHello());
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.advanceTimersByTimeAsync(9999);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(10000);
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(body).toContain("Hello.");
    expect(errorTextFrom(body)).toBeUndefined();
  } finally {
    vi.useRealTimers();
  }
});

it("clamps an excessive Retry-After to the boot delay ceiling", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(boot503("3600"))
      .mockResolvedValue(sseHello());
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.advanceTimersByTimeAsync(29999);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    await vi.runAllTimersAsync();
    expect(errorTextFrom(await pendingBody)).toBeUndefined();
  } finally {
    vi.useRealTimers();
  }
});

it("floors a zero Retry-After so a boot 503 cannot hot-loop", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(boot503("0"))
      .mockResolvedValue(sseHello());
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.advanceTimersByTimeAsync(999);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    await vi.runAllTimersAsync();
    expect(errorTextFrom(await pendingBody)).toBeUndefined();
  } finally {
    vi.useRealTimers();
  }
});

// Retry-After is honored on the boot code ONLY: a non-boot 503 keeps the
// fixed 2s/5s/8s delays and the 4-attempt budget even when it carries one.
it("ignores Retry-After on a non-boot 503 and keeps the short budget", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: "overloaded" } }), {
          status: 503,
          headers: { "retry-after": "30" },
        }),
      )
      .mockResolvedValue(sseHello());
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.advanceTimersByTimeAsync(1999);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(body).not.toContain("warming_up");
    expect(body).toContain("Hello.");
  } finally {
    vi.useRealTimers();
  }
});

it("keeps the short budget when a non-boot 503 never recovers", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => boot503("30", JSON.stringify({ code: "overloaded" })));
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(fetchSpy).toHaveBeenCalledTimes(4);
    expect(body).not.toContain("warming_up");
    expect(body).not.toContain('"type":"text-delta"');
    expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
    expect(errorLog).toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});

// Time bound: Retry-After 5s polls floor(250s / 5s) + 1 = 51 times, then the
// turn fails with the unavailable-message instead of retrying forever.
it("exhausts the boot budget on a boot that never ends", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => boot503("5"));
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(fetchSpy).toHaveBeenCalledTimes(
      Math.floor(UPSTREAM_BOOT_MAX_ELAPSED_MS / 5000) + 1,
    );
    expect(body).not.toContain('"type":"text-delta"');
    expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
    expect(errorLog).toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});

// Attempt bound: the backstop when the clock cannot be trusted.
it("caps boot attempts even when the budget has not elapsed", async () => {
  vi.useFakeTimers();
  try {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => boot503("1"));
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(fetchSpy).toHaveBeenCalledTimes(UPSTREAM_BOOT_MAX_ATTEMPTS);
    expect(errorTextFrom(body)).toBe(DIGIGRAPH_UNAVAILABLE_MESSAGE);
  } finally {
    vi.useRealTimers();
  }
});

it("stops a boot wait when the request is aborted", async () => {
  vi.useFakeTimers();
  try {
    const controller = new AbortController();
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(boot503("30"));
    vi.spyOn(console, "error").mockImplementation(() => {});

    const pendingBody = streamBody({ signal: controller.signal });
    await vi.advanceTimersByTimeAsync(100);
    controller.abort();
    await vi.runAllTimersAsync();
    const body = await pendingBody;

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(errorTextFrom(body)).toBeTruthy();
  } finally {
    vi.useRealTimers();
  }
});
