import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";
import {
  isPrivateMode,
  PRIVATE_MODE_INSTRUCTION,
  PRIVATE_MODE_MESSAGE_ID,
  privateModeInstructionText,
  separatePrivateInstructionPayload,
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
  it("inserts the instruction as its own user message before the last user turn", () => {
    const messages = [user("first"), assistant("ok"), user("John Smith", "u2")];
    const out = withPrivateModeUiPrompt(messages);

    expect(out).toHaveLength(4);
    expect(textOf(out[0])).toBe("first");
    expect(textOf(out[1])).toBe("ok");
    expect(out[2]?.id).toBe(PRIVATE_MODE_MESSAGE_ID);
    expect(textOf(out[2])).toBe(PRIVATE_MODE_INSTRUCTION);
    expect(textOf(out[3])).toBe("John Smith");
    expect(privateModeInstructionText(out)).toBe(PRIVATE_MODE_INSTRUCTION);
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
    const carrying = out.filter((m) => textOf(m).includes("PRIVATE DEMO SESSION"));
    expect(carrying).toHaveLength(1);
    expect(out[4]?.id).toBe(PRIVATE_MODE_MESSAGE_ID);
    expect(textOf(out[5])).toBe("e");
  });

  it("leaves a non-text part on the typed turn and does not copy it onto the instruction", () => {
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
    expect(out[0]?.id).toBe(PRIVATE_MODE_MESSAGE_ID);
    expect(out[0]?.parts).toEqual([{ type: "text", text: PRIVATE_MODE_INSTRUCTION }]);
    expect(out[1]?.parts).toHaveLength(2);
    expect(out[1]?.parts[1]).toMatchObject({ type: "file" });
  });

  it("returns the messages untouched when there is no user turn", () => {
    const messages = [assistant("only")];
    expect(withPrivateModeUiPrompt(messages)).toEqual(messages);
    expect(privateModeInstructionText(messages)).toBeNull();
  });

  it("does not insert a second instruction when one is already present", () => {
    const once = withPrivateModeUiPrompt([user("John Smith")]);
    expect(withPrivateModeUiPrompt(once)).toBe(once);
  });
});

describe("separatePrivateInstructionPayload", () => {
  it("splits a glued instruction off the typed text and leaves the question last", () => {
    const glued = `notes\n\n${PRIVATE_MODE_INSTRUCTION}\n\nJohn Smith at Acme`;
    const out = separatePrivateInstructionPayload([{ role: "user", content: glued }]);
    expect(out).toEqual([
      { role: "user", content: PRIVATE_MODE_INSTRUCTION },
      { role: "user", content: "notes\n\nJohn Smith at Acme" },
    ]);
  });

  it("leaves an already-separate instruction and every other message unchanged", () => {
    const tool = {
      role: "tool",
      content: JSON.stringify({ ticket: "ACME-1", name: "John Smith" }),
    };
    const out = separatePrivateInstructionPayload([
      { role: "user", content: PRIVATE_MODE_INSTRUCTION },
      { role: "user", content: "John Smith" },
      tool,
      { role: "assistant", content: "ticket ACME-1 belongs to John Smith" },
    ]);
    expect(out[0]).toEqual({ role: "user", content: PRIVATE_MODE_INSTRUCTION });
    expect(out[1]).toEqual({ role: "user", content: "John Smith" });
    expect(out[2]).toBe(tool);
    expect(out[3]?.content).toBe("ticket ACME-1 belongs to John Smith");
  });

  it("does nothing when private mode is off", () => {
    const messages = [
      { role: "user", content: "John Smith" },
      { role: "assistant", content: "hello John" },
    ];
    expect(separatePrivateInstructionPayload(messages)).toEqual(messages);
  });
});

describe("PRIVATE_MODE_INSTRUCTION content", () => {
  it("covers tool results and hides the product behind a generic support desk", () => {
    expect(PRIVATE_MODE_INSTRUCTION).toMatch(/tool results/);
    expect(PRIVATE_MODE_INSTRUCTION).toMatch(/generic support assistant/);
    expect(PRIVATE_MODE_INSTRUCTION).toMatch(/Never name the product/);
    expect(PRIVATE_MODE_INSTRUCTION).toMatch(/never repeat an original value/);
  });

  it("names no product, tenant or ticketing system itself", () => {
    for (const name of ["OCC", "digithings", "DigiChat"]) {
      expect(PRIVATE_MODE_INSTRUCTION.toLowerCase()).not.toContain(name.toLowerCase());
    }
  });
});
