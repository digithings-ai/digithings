import { it, expect, vi, afterEach } from "vitest";
import type { UIMessage } from "ai";
import { createDigigraphTraceStreamResponse } from "./stream-digigraph-trace";

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
    upstreamBearer: "tok",
    activityDetail: "full",
    emitLegacyTracePart: true,
  });
  const body = await new Response(res.body).text();

  expect(body).not.toContain(secret);
  expect(body).not.toContain("db.internal");
  expect(body).toMatch(/unavailable|try again/i);
  expect(errorLog).toHaveBeenCalled();
});

// The authenticated (non-embed) chat surface renders data-digigraphTrace via
// chat-panel.tsx's DigigraphTraceBlock, which Task 6 broke by switching this
// provider to emit only data-digichatActivity. The fix is to dual-emit on the
// authenticated path: the legacy part carries the original full
// DigigraphTracePayload (ungated, as it always did before Task 6) alongside
// the new gated activity span, so chat-panel.tsx keeps working unchanged. The
// legacy part is NOT emitted on the embed path (where emitLegacyTracePart:false).
it("dual-emits both the legacy digigraphTrace part and the new gated activity span on the authenticated path", async () => {
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
    upstreamBearer: "tok",
    activityDetail: "full",
    emitLegacyTracePart: true,
  });
  const body = await new Response(res.body).text();

  // Legacy part: full original payload, present on authenticated path.
  expect(body).toContain('"type":"data-digigraphTrace"');
  expect(body).toContain('"workflow_id":"wf-1"');
  expect(body).toContain('"label":"Searching…"');
  // New part: gated span alongside it.
  expect(body).toContain('"type":"data-digichatActivity"');
  expect(body).toContain('"operation":"chat"');
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
    upstreamBearer: "tok",
    activityDetail: "off",
    emitLegacyTracePart: false,
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
    upstreamBearer: "tok",
    activityDetail: "full",
    emitLegacyTracePart: false,
  });
  const body = await new Response(res.body).text();

  // Activity span present on embed path with activityDetail: full.
  expect(body).toContain('"type":"data-digichatActivity"');
  expect(body).toContain('"operation":"chat"');
  // But legacy part is NOT emitted on embed path.
  expect(body).not.toContain('"type":"data-digigraphTrace"');
  expect(body).not.toContain('"workflow_id"');
});
