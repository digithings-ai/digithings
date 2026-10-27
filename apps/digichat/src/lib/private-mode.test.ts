import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";
import {
  isPrivateMode,
  PRIVATE_MODE_INSTRUCTION,
  withPrivateModeUiPrompt,
} from "./private-mode";

const user = (text: string, id = "u1"): UIMessage => ({
  id,
  role: "user",
  parts: [{ type: "text", text }],
});

const assistant = (text: string, id = "a1"): UIMessage => ({
  id,
  role: "assistant",
  parts: [{ type: "text", text }],
});

const textOf = (message: UIMessage | undefined): string =>
  (message?.parts ?? [])
    .filter((part) => part.type === "text")
    .map((part) => (part as { text: string }).text)
    .join("");

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

describe("withPrivateModeUiPrompt", () => {
  it("appends the instruction to the last user turn and nothing else", () => {
    const messages = [user("first"), assistant("ok"), user("John Smith", "u2")];
    const out = withPrivateModeUiPrompt(messages);

    expect(out).toHaveLength(3);
    expect(textOf(out[0])).toBe("first");
    expect(textOf(out[1])).toBe("ok");
    expect(textOf(out[2])).toBe(`John Smith\n\n${PRIVATE_MODE_INSTRUCTION}`);
  });

  it("does not mutate the input", () => {
    const messages = [user("John Smith")];
    withPrivateModeUiPrompt(messages);
    expect(textOf(messages[0])).toBe("John Smith");
    expect(messages[0]?.parts).toHaveLength(1);
  });

  it("applies the instruction exactly once across a long turn list", () => {
    const out = withPrivateModeUiPrompt([
      user("a", "u1"),
      assistant("b", "a1"),
      user("c", "u2"),
      assistant("d", "a2"),
      user("e", "u3"),
    ]);
    const carrying = out.filter((m) =>
      textOf(m).includes("PRIVATE DEMO SESSION"),
    );
    expect(carrying).toHaveLength(1);
    expect(textOf(out[4])).toContain("PRIVATE DEMO SESSION");
  });

  it("keeps a non-text part that already sits in the user turn", () => {
    const messages: UIMessage[] = [
      {
        id: "u1",
        role: "user",
        parts: [
          { type: "text", text: "look at this" },
          { type: "file", mediaType: "application/pdf", url: "blob:x" },
        ],
      },
    ];
    const out = withPrivateModeUiPrompt(messages);
    expect(out[0]?.parts).toHaveLength(3);
    expect(out[0]?.parts[1]).toMatchObject({ type: "file" });
  });

  it("returns the messages untouched when there is no user turn", () => {
    const messages = [assistant("only")];
    expect(withPrivateModeUiPrompt(messages)).toEqual(messages);
  });
});
