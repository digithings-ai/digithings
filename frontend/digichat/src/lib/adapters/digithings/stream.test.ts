import { it, expect, vi, afterEach } from "vitest";
import type { UIMessage } from "ai";
import {
  createDigigraphTraceStreamResponse,
  digigraphErrorToEmbedPayload,
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
  expect(body).toMatch(/unavailable|try again/i);
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
// JSON, which is worse than the generic message.
it("still swallows an error code that is not on the allowlist", async () => {
  const { body, errorLog } = await streamFor400(
    JSON.stringify({
      error: { code: "thread_error", message: "Traceback: connect to db.internal:5432" },
    }),
  );

  expect(body).not.toContain("thread_error");
  expect(body).not.toContain("db.internal");
  expect(body).toMatch(/unavailable|try again/i);
  expect(errorLog).toHaveBeenCalled();
});

it("still swallows a body that is not JSON", async () => {
  const { body } = await streamFor400("<html>502 Bad Gateway from nginx/1.25</html>");
  expect(body).not.toContain("nginx");
  expect(body).toMatch(/unavailable|try again/i);
});
