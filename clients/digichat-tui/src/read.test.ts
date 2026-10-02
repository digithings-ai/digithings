import { expect, test } from "bun:test";
import {
  CREDIT,
  PLACEHOLDER,
  WELCOME,
  assembleScreen,
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

  const screen = assembleScreen(
    interpretStatus(502, closed),
    interpretStatus(502, closed),
    interpretStatus(502, closed),
  );
  expect(screen.status).toBe("empty");
  expect(screen.sessions).toEqual([]);
  expect(screen.messages).toEqual([]);
  expect(screen.welcome).toBe(false);
  expect(screen.note).toBe("digichat is not configured");
  expect(screen.note).not.toContain("What should we inspect");
});

test("a live empty payload shows the welcome and no fabricated messages", () => {
  const screen = assembleScreen(
    interpretStatus(200, { data: { sessions: [] } }),
    interpretStatus(200, { data: { id: null, title: null } }),
    interpretStatus(200, { data: { messages: [] } }),
  );
  expect(screen.status).toBe("empty");
  expect(screen.welcome).toBe(true);
  expect(screen.messages).toEqual([]);
  expect(screen.sessions).toEqual([]);
  expect(WELCOME).toBe("What should we inspect?");
  expect(PLACEHOLDER).toBe("Ask digichat…");
  expect(CREDIT).toBe("powered by digichat — a digithings product.");
});

test("sessions, the current thread, and messages come from the payload", () => {
  expect(sessionRows({ sessions: [{ id: "s1", title: "  book  " }, { id: "", title: "nope" }, { title: "x" }] })).toEqual([
    { id: "s1", title: "book" },
  ]);
  expect(sessionRows({ sessions: [{ id: "s2", title: "  " }] })).toEqual([{ id: "s2", title: "—" }]);
  expect(
    messageRows({
      messages: [
        { id: "m1", role: "user", text: "what is flat" },
        { id: "m2", role: "assistant", text: "the book is flat" },
        { role: "tool", tool: { name: "book" } },
      ],
    }),
  ).toEqual([
    { id: "m1", role: "user", text: "what is flat", tool: null, reasoning: "", at: "" },
    { id: "m2", role: "assistant", text: "the book is flat", tool: null, reasoning: "", at: "" },
    { id: "row-2", role: "assistant", text: "book", tool: { name: "book", status: "", detail: "" }, reasoning: "", at: "" },
  ]);

  const screen = assembleScreen(
    interpretStatus(200, { data: { sessions: [{ id: "s1", title: "book" }] } }),
    interpretStatus(200, { data: { id: "s1", title: "book" } }),
    interpretStatus(200, {
      data: { messages: [{ id: "m1", role: "user", text: "what is flat" }] },
    }),
  );
  expect(screen.status).toBe("ok");
  expect(screen.welcome).toBe(false);
  expect(screen.currentId).toBe("s1");
  expect(screen.messages).toHaveLength(1);
});

test("a non-empty failure is an error and still paints no thread", () => {
  const screen = assembleScreen(
    interpretStatus(500, { error: { message: "boom" } }),
    interpretStatus(200, { data: { id: "s1", title: "book" } }),
    interpretStatus(200, { data: { messages: [{ id: "m1", role: "user", text: "hi" }] } }),
  );
  expect(screen.status).toBe("error");
  expect(screen.sessions).toEqual([]);
  expect(screen.messages).toEqual([]);
  expect(screen.welcome).toBe(false);
  expect(screen.note).toContain("boom");
});
