import { expect, test } from "bun:test";
import {
  AUTH_REQUIRED,
  CREDIT,
  PLACEHOLDER,
  WELCOME,
  assembleFromBff,
  chatBaseUrl,
  mcpRowsFromTenantConfig,
  modelRowsFromByok,
  interpretChatStream,
  interpretStatus,
  messageRows,
  sessionRows,
} from "./read";

const closed = {
  error: { code: "upstream_empty", message: "digichat is not configured" },
};

test("502 and 503 stay an empty read and do not invent a thread", () => {
  const denied = interpretStatus(502, closed);
  expect(denied.kind).toBe("empty");
  expect(denied.note).toBe("digichat is not configured");
  expect(denied.data).toBeNull();

  const down = interpretStatus(503, {
    error: { code: "not_provisioned", message: "chat send is not provisioned" },
  });
  expect(down.kind).toBe("empty");
  expect(down.note).toBe("chat send is not provisioned");

  const screen = assembleFromBff(interpretStatus(502, closed), null, null);
  expect(screen.status).toBe("empty");
  expect(screen.sessions).toEqual([]);
  expect(screen.messages).toEqual([]);
  expect(screen.welcome).toBe(false);
  expect(screen.note).toBe("digichat is not configured");
  expect(screen.note).not.toContain("What should we inspect");
});

test("401 asks for a DigiChat machine key", () => {
  const denied = interpretStatus(401, { error: "unauthorized", message: "Sign in" });
  expect(denied.kind).toBe("error");
  expect(denied.note).toContain("Sign in");
  expect(AUTH_REQUIRED).toContain("DIGICHAT_API_KEY");
});

test("a live empty payload shows the welcome and no fabricated messages", () => {
  const screen = assembleFromBff(
    interpretStatus(200, { serverPersistence: true, conversations: [] }),
    null,
    null,
  );
  expect(screen.status).toBe("empty");
  expect(screen.welcome).toBe(true);
  expect(screen.messages).toEqual([]);
  expect(screen.sessions).toEqual([]);
  expect(WELCOME).toBe("What should we inspect?");
  expect(PLACEHOLDER).toBe("Ask digichat…");
  expect(CREDIT).toBe("powered by digichat — a digithings product.");
});

test("conversations and UIMessage parts come from the BFF payload", () => {
  expect(
    sessionRows({
      conversations: [{ id: "s1", title: "  book  " }, { id: "", title: "nope" }, { title: "x" }],
    }),
  ).toEqual([{ id: "s1", title: "book" }]);
  expect(sessionRows({ conversations: [{ id: "s2", title: "  " }] })).toEqual([
    { id: "s2", title: "—" },
  ]);
  expect(
    messageRows({
      messages: [
        { id: "m1", role: "user", parts: [{ type: "text", text: "what is flat" }] },
        { id: "m2", role: "assistant", parts: [{ type: "text", text: "the book is flat" }] },
        {
          id: "m3",
          role: "assistant",
          parts: [{ type: "tool-book", toolName: "book", state: "output-available" }],
        },
      ],
    }),
  ).toEqual([
    { id: "m1", role: "user", text: "what is flat", tool: null, reasoning: "", at: "" },
    { id: "m2", role: "assistant", text: "the book is flat", tool: null, reasoning: "", at: "" },
    {
      id: "m3",
      role: "assistant",
      text: "book",
      tool: { name: "book", status: "output-available", detail: "" },
      reasoning: "",
      at: "",
    },
  ]);

  const screen = assembleFromBff(
    interpretStatus(200, { conversations: [{ id: "s1", title: "book" }] }),
    interpretStatus(200, {
      id: "s1",
      title: "book",
      messages: [{ id: "m1", role: "user", parts: [{ type: "text", text: "what is flat" }] }],
    }),
    "s1",
  );
  expect(screen.status).toBe("ok");
  expect(screen.welcome).toBe(false);
  expect(screen.currentId).toBe("s1");
  expect(screen.messages).toHaveLength(1);
});

test("a non-empty failure is an error and still paints no thread", () => {
  const screen = assembleFromBff(
    interpretStatus(500, { error: { message: "boom" } }),
    interpretStatus(200, { id: "s1", title: "book", messages: [] }),
    "s1",
  );
  expect(screen.status).toBe("error");
  expect(screen.sessions).toEqual([]);
  expect(screen.messages).toEqual([]);
  expect(screen.welcome).toBe(false);
  expect(screen.note).toContain("boom");
});

test("chat stream text-deltas join into a reply", () => {
  const raw = [
    'data: {"type":"text-start","id":"t1"}',
    'data: {"type":"text-delta","id":"t1","delta":"Hi"}',
    'data: {"type":"text-delta","id":"t1","delta":" there"}',
    "data: [DONE]",
    "",
  ].join("\n");
  expect(interpretChatStream(200, raw, "text/event-stream")).toEqual({
    kind: "text",
    text: "Hi there",
  });
});

test("chat base URL is the surface-config chat endpoint, not the desk runner", () => {
  expect(chatBaseUrl({ DQ_API_URL: "http://127.0.0.1:8788" })).toBe("http://127.0.0.1:3000");
  expect(chatBaseUrl({ DIGI_CHAT_URL: "http://127.0.0.1:3005/" })).toBe("http://127.0.0.1:3005");
});

test("BYOK model buckets flatten to ids without inventing names", () => {
  expect(
    modelRowsFromByok({
      ok: true,
      free: [{ id: "a/free", name: "Free A" }, { id: "a/free" }],
      flagship: [{ id: "b/paid" }],
    }),
  ).toEqual([
    { id: "a/free", label: "Free A" },
    { id: "b/paid", label: "b/paid" },
  ]);
});

test("MCP tenant-config projects ids and labels only", () => {
  expect(
    mcpRowsFromTenantConfig({
      mcp: {
        servers: [
          { id: "datatap", label: "DataTap", url: "https://secret.example/mcp" },
          { id: "" },
          { id: "vault" },
        ],
      },
    }),
  ).toEqual([
    { id: "datatap", label: "DataTap" },
    { id: "vault", label: "vault" },
  ]);
});
