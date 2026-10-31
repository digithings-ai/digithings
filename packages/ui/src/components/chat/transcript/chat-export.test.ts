import { describe, expect, it } from "vitest";

import {
  CHAT_EXPORT_FORMATS,
  chatExportLabel,
  chatExportStrings,
  conversationMarkdown,
  lastQuestion,
  messageMarkdown,
  parseChatExportFormat,
  transcriptTurn,
  transcriptTurns,
} from "./chat-export";

const messages = [
  { id: "u1", role: "user", content: [{ type: "text", text: "What moved overnight?" }] },
  {
    id: "a1",
    role: "assistant",
    content: [
      { type: "reasoning", text: "thinking out loud" },
      { type: "tool-call", toolName: "search", args: {} },
      { type: "text", text: "Rates were **flat**." },
    ],
  },
  { id: "s1", role: "system", content: [{ type: "text", text: "hidden" }] },
  { id: "u2", role: "user", parts: [{ type: "text", text: "And the curve?" }] },
  { id: "a2", role: "assistant", content: "It steepened." },
  { id: "a3", role: "assistant", content: [{ type: "text", text: "   " }] },
];

describe("parseChatExportFormat", () => {
  it("reads md, markdown, html and htm; empty is markdown", () => {
    expect(parseChatExportFormat("")).toBe("md");
    expect(parseChatExportFormat(undefined)).toBe("md");
    expect(parseChatExportFormat(" MD ")).toBe("md");
    expect(parseChatExportFormat(".md")).toBe("md");
    expect(parseChatExportFormat("markdown")).toBe("md");
    expect(parseChatExportFormat("HTML")).toBe("html");
    expect(parseChatExportFormat("htm")).toBe("html");
    expect(parseChatExportFormat("pdf")).toBeNull();
    expect(CHAT_EXPORT_FORMATS).toEqual(["md", "html"]);
  });
});

describe("chatExportStrings", () => {
  it("has English and French, and falls back to English", () => {
    expect(chatExportStrings("en").export).toBe("Export");
    expect(chatExportStrings("fr").export).toBe("Exporter");
    expect(chatExportStrings("fr-CA").user).toBe("Utilisateur");
    expect(chatExportStrings("de").export).toBe("Export");
    expect(chatExportStrings(null).markdown).toBe("Markdown (.md)");
    expect(chatExportLabel("md", chatExportStrings())).toBe("Markdown (.md)");
    expect(chatExportLabel("html", chatExportStrings("fr"))).toBe("HTML (.html)");
  });
});

describe("transcriptTurns", () => {
  it("keeps user and assistant text, in order, from content or parts", () => {
    expect(transcriptTurns(messages)).toEqual([
      { role: "user", content: "What moved overnight?" },
      { role: "assistant", content: "Rates were **flat**." },
      { role: "user", content: "And the curve?" },
      { role: "assistant", content: "It steepened." },
    ]);
    expect(transcriptTurn(null)).toBeNull();
  });
});

describe("conversationMarkdown", () => {
  it("labels every turn User / Assistant and keeps them apart", () => {
    const md = conversationMarkdown(transcriptTurns(messages));
    expect(md).toBe(
      [
        "## User\n\nWhat moved overnight?",
        "## Assistant\n\nRates were **flat**.",
        "## User\n\nAnd the curve?",
        "## Assistant\n\nIt steepened.",
      ].join("\n\n---\n\n"),
    );
    expect(md).not.toContain("thinking out loud");
    expect(md).not.toContain("hidden");
  });

  it("uses the session language for the headings", () => {
    const md = conversationMarkdown(transcriptTurns(messages), chatExportStrings("fr"));
    expect(md.startsWith("## Utilisateur\n\n")).toBe(true);
    expect(md).toContain("## Assistant\n\nIt steepened.");
  });

  it("is empty for an empty thread", () => {
    expect(conversationMarkdown([])).toBe("");
  });
});

describe("messageMarkdown", () => {
  it("is the answer alone, without a heading or the question", () => {
    expect(messageMarkdown(transcriptTurn(messages[1]))).toBe("Rates were **flat**.");
    expect(messageMarkdown(transcriptTurn(messages[0]))).toBe("");
    expect(messageMarkdown(null)).toBe("");
  });

  it("names the file after the last question", () => {
    expect(lastQuestion(transcriptTurns(messages))).toBe("And the curve?");
    expect(lastQuestion([])).toBe("");
  });
});
