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
  });
  const body = await new Response(res.body).text();

  expect(body).not.toContain(secret);
  expect(body).not.toContain("db.internal");
  expect(body).toMatch(/unavailable|try again/i);
  expect(errorLog).toHaveBeenCalled();
});
