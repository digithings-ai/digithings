import { readFileSync } from "node:fs";
import { expect, test } from "bun:test";
import { CHAT_CLOSED } from "./chat-format";

test("the terminal draws chat inside the existing rail", () => {
  const app = readFileSync(new URL("../app.tsx", import.meta.url), "utf8");
  const page = readFileSync(new URL("./chat.tsx", import.meta.url), "utf8");
  expect(app).toContain("<ChatPage");
  expect(app).toContain("stepRailCols");
  expect(app).toContain(">threads<");
  expect(app).not.toContain("Chat · sessions");
  expect(page).toContain("chatFailureSentence");
  expect(page).not.toContain("DigichatThreadList");
  expect(page).not.toContain("Chat · transcript");
  expect(CHAT_CLOSED).toBe("digichat is not configured.");
});
