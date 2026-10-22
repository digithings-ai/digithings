import { afterEach, describe, expect, it, vi } from "vitest";
import { warmFetch } from "@/lib/warmup-gate";

/**
 * The client-side retry that the cold-digikey answer depends on.
 *
 * digichat answers a cold digikey with `503 upstream_unavailable` and a
 * `Retry-After`, and the browser has to repeat the send. The list of bodies
 * that count as transient is load-bearing and used to be unpinned: losing the
 * `upstream_unavailable` token silently took the retry away, and the cold case
 * then ended at the visitor as a failed turn (DIG-4424).
 */

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** A fetch double: the warm-up probe answers "ready", the chat call follows the script. */
function chatFetch(script: Response[]) {
  let chatAttempt = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/embed/warmup")) {
      return jsonResponse({ ready: true, services: { assistant: "ready" } });
    }
    const next = script[Math.min(chatAttempt, script.length - 1)];
    chatAttempt += 1;
    return next;
  });
  return { fetchMock, attempts: () => chatAttempt };
}

const COLD_BODY = {
  error: "upstream_unavailable",
  message:
    "digikey did not answer the bff_session exchange — it is cold or unreachable (last answer: 503). This is not a DIGIKEY_BFF_TOKEN problem; retry in a few seconds.",
};

const REFUSED_BODY = {
  error: "upstream_auth",
  message:
    "digikey rejected the bff_session exchange (answered 401). Check DIGIKEY_BFF_TOKEN and digikey configuration.",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("warmFetch", () => {
  it("re-sends the request when digikey is cold (503 upstream_unavailable)", async () => {
    const { fetchMock, attempts } = chatFetch([
      jsonResponse(COLD_BODY, 503),
      jsonResponse({ ok: true }, 200),
    ]);
    vi.stubGlobal("fetch", fetchMock);

    const res = await warmFetch("/api/chat", { method: "POST", body: "{}" });

    expect(res.status).toBe(200);
    expect(attempts()).toBe(2);
  });

  it("re-sends the request on the refused-token answer too (502 upstream_auth)", async () => {
    // The two shapes must not drift apart: both are digikey answers the client
    // has to survive by repeating the send.
    const { fetchMock, attempts } = chatFetch([
      jsonResponse(REFUSED_BODY, 502),
      jsonResponse({ ok: true }, 200),
    ]);
    vi.stubGlobal("fetch", fetchMock);

    const res = await warmFetch("/api/chat", { method: "POST", body: "{}" });

    expect(res.status).toBe(200);
    expect(attempts()).toBe(2);
  });

  it("does not re-send a 5xx whose body is not transient", async () => {
    const { fetchMock, attempts } = chatFetch([
      jsonResponse({ error: "quota_exceeded", message: "too many requests" }, 503),
    ]);
    vi.stubGlobal("fetch", fetchMock);

    const res = await warmFetch("/api/chat", { method: "POST", body: "{}" });

    expect(res.status).toBe(503);
    expect(attempts()).toBe(1);
  });

  it("does not re-send a 4xx", async () => {
    const { fetchMock, attempts } = chatFetch([
      jsonResponse({ error: "upstream_auth", message: "refused" }, 401),
    ]);
    vi.stubGlobal("fetch", fetchMock);

    const res = await warmFetch("/api/chat", { method: "POST", body: "{}" });

    expect(res.status).toBe(401);
    expect(attempts()).toBe(1);
  });
});
