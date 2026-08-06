import { describe, it, expect, vi, afterEach } from "vitest";
import type { UIMessage } from "ai";
import { createDigivaultStreamResponse } from "./digivault-stream";
import type { DigivaultResolvedEnv } from "./digivault-env";

afterEach(() => vi.restoreAllMocks());

const env: DigivaultResolvedEnv = {
  supabaseUrl: "https://example.supabase.co",
  supabaseAnonKey: "anon",
  openRouterKey: "sk-or-pool",
};

function userMessage(text: string): UIMessage {
  return { id: "u1", role: "user", parts: [{ type: "text", text }] } as UIMessage;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("createDigivaultStreamResponse", () => {
  it("writes activity parts and text deltas for a tool+answer turn", async () => {
    let llmCalls = 0;
    const fetchImpl: typeof fetch = async (input) => {
      const url = String(input);
      if (url.includes("search_architecture_notes")) {
        return jsonResponse([
          {
            vault_path: "arch/ports.md",
            title: "Ports",
            body_markdown: "# secret body that must not leak",
          },
        ]);
      }
      llmCalls += 1;
      if (llmCalls === 1) {
        return jsonResponse({
          choices: [
            {
              message: {
                role: "assistant",
                content: "",
                tool_calls: [
                  {
                    id: "tc1",
                    type: "function",
                    function: {
                      name: "search_digivault",
                      arguments: JSON.stringify({ query: "ports" }),
                    },
                  },
                ],
              },
            },
          ],
        });
      }
      return jsonResponse({
        choices: [
          {
            message: {
              role: "assistant",
              content: "Digigraph listens on port 8000.",
            },
          },
        ],
      });
    };

    const res = await createDigivaultStreamResponse({
      messages: [userMessage("what ports?")],
      env,
      responseHeaders: {},
      activityDetail: "full",
      fetchImpl,
    });
    const body = await new Response(res.body).text();
    expect(body).toContain('"type":"data-digichatActivity"');
    expect(body).toContain("search_digivault");
    expect(body).toContain("Digigraph listens on port 8000.");
    expect(body).not.toContain("body_markdown");
    expect(body).not.toContain("# secret");
  });

  it("returns generic browser error and logs upstream failures", async () => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});
    const fetchImpl: typeof fetch = async (input) => {
      const url = String(input);
      if (url.includes("search_architecture_notes")) {
        return jsonResponse([]);
      }
      return new Response("Traceback (most recent call last):\n  File secret.py", {
        status: 500,
      });
    };

    const res = await createDigivaultStreamResponse({
      messages: [userMessage("hi")],
      env,
      responseHeaders: {},
      activityDetail: "full",
      fetchImpl,
    });
    const body = await new Response(res.body).text();
    expect(body).not.toContain("Traceback");
    expect(body).toMatch(/unavailable|try again/i);
    expect(errorLog).toHaveBeenCalled();
  });

  it("honours activityDetail labels (no documents on wire)", async () => {
    let llmCalls = 0;
    const fetchImpl: typeof fetch = async (input) => {
      const url = String(input);
      if (url.includes("search_architecture_notes")) {
        return jsonResponse([
          {
            vault_path: "arch/ports.md",
            title: "Ports",
            body_markdown: "# secret body",
          },
        ]);
      }
      llmCalls += 1;
      if (llmCalls === 1) {
        return jsonResponse({
          choices: [
            {
              message: {
                role: "assistant",
                content: "",
                tool_calls: [
                  {
                    id: "tc1",
                    type: "function",
                    function: {
                      name: "search_digivault",
                      arguments: JSON.stringify({ query: "ports" }),
                    },
                  },
                ],
              },
            },
          ],
        });
      }
      return jsonResponse({
        choices: [{ message: { role: "assistant", content: "Answer." } }],
      });
    };

    const res = await createDigivaultStreamResponse({
      messages: [userMessage("ports?")],
      env,
      responseHeaders: {},
      activityDetail: "labels",
      fetchImpl,
    });
    const body = await new Response(res.body).text();
    expect(body).toContain('"type":"data-digichatActivity"');
    expect(body).toContain("documentsWithheld");
    expect(body).not.toContain('"documents"');
    expect(body).not.toContain("arch/ports.md");
    expect(body).not.toContain("# secret");
  });
});
