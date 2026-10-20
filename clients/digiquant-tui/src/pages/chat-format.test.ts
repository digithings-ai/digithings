import { expect, test } from "bun:test";
import { CHAT_CLOSED, chatFailureSentence } from "./chat-format";

test("three unconfigured chat reads collapse to one sentence", () => {
  const lines = [
    "/chat/sessions failed (502): digichat is not configured",
    "/chat/sessions/current failed (502): digichat is not configured",
    "/chat/sessions/current/messages failed (502): digichat is not configured",
  ];
  expect(chatFailureSentence(lines)).toBe(CHAT_CLOSED);
  expect(CHAT_CLOSED).toBe("digichat is not configured.");
});

test("a different chat failure stays one sentence", () => {
  expect(chatFailureSentence(["/chat/sessions: the official API could not be reached."])).toBe(
    "the official API could not be reached.",
  );
  expect(chatFailureSentence([])).toBeNull();
});
