import { describe, expect, it } from "vitest";
import type { ModelMessage } from "ai";
import {
  isPrivateMode,
  PRIVATE_MODE_INSTRUCTION,
  withPrivateModePrompt,
} from "./private-mode";

const user = (content: string): ModelMessage => ({ role: "user", content });
const assistant = (content: string): ModelMessage => ({
  role: "assistant",
  content,
});

describe("isPrivateMode", () => {
  it("accepts only an exact 1, trimmed", () => {
    expect(isPrivateMode(new Headers({ "x-digi-private": "1" }))).toBe(true);
    expect(isPrivateMode(new Headers({ "x-digi-private": " 1 " }))).toBe(true);
  });

  it("refuses everything else", () => {
    expect(isPrivateMode(new Headers())).toBe(false);
    expect(isPrivateMode(new Headers({ "x-digi-private": "" }))).toBe(false);
    expect(isPrivateMode(new Headers({ "x-digi-private": "0" }))).toBe(false);
    expect(isPrivateMode(new Headers({ "x-digi-private": "11" }))).toBe(false);
    expect(isPrivateMode(new Headers({ "x-digi-private": "true" }))).toBe(false);
  });
});

describe("withPrivateModePrompt", () => {
  it("appends the instruction to the last user turn and nothing else", () => {
    const messages = [user("first"), assistant("ok"), user("John Smith")];
    const out = withPrivateModePrompt(messages);

    expect(out).toHaveLength(3);
    expect(out[0]).toEqual(user("first"));
    expect(out[1]).toEqual(assistant("ok"));
    expect(out[2]?.content).toBe(
      `John Smith\n\n${PRIVATE_MODE_INSTRUCTION}`,
    );
  });

  it("does not mutate the input", () => {
    const messages = [user("John Smith")];
    withPrivateModePrompt(messages);
    expect(messages[0]?.content).toBe("John Smith");
  });

  it("applies the instruction exactly once across turns", () => {
    const out = withPrivateModePrompt([
      user("a"),
      assistant("b"),
      user("c"),
      assistant("d"),
      user("e"),
    ]);
    const occurrences = out.filter(
      (m) =>
        typeof m.content === "string" &&
        m.content.includes("PRIVATE DEMO SESSION"),
    );
    expect(occurrences).toHaveLength(1);
    expect(out[4]?.content).toContain("PRIVATE DEMO SESSION");
  });

  it("appends a text part when the content is an array", () => {
    const messages: ModelMessage[] = [
      { role: "user", content: [{ type: "text", text: "hi" }] },
    ];
    const out = withPrivateModePrompt(messages);
    const content = out[0]?.content;
    expect(Array.isArray(content)).toBe(true);
    if (!Array.isArray(content)) throw new Error("expected parts");
    expect(content).toHaveLength(2);
    expect(content[1]).toEqual({
      type: "text",
      text: PRIVATE_MODE_INSTRUCTION,
    });
  });

  it("returns the messages untouched when there is no user turn", () => {
    const messages = [assistant("only")];
    expect(withPrivateModePrompt(messages)).toEqual(messages);
  });
});
