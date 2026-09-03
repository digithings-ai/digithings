/**
 * Serializer + embed fallback for turn / thread markdown export (#3465).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  copyMarkdownWithFallback,
  downloadMarkdown,
  serializeAssistantMarkdown,
  serializeThreadMarkdown,
} from "./transcript-markdown";

describe("serializeAssistantMarkdown", () => {
  it("strips Foundry citation markers and keeps prose", () => {
    const md = serializeAssistantMarkdown("Hello【9:0†source】 world");
    expect(md).toContain("Hello");
    expect(md).toContain("world");
    expect(md).not.toContain("source");
    expect(md).not.toContain("\u3010");
  });

  it("appends Sources title+path only — never body", () => {
    const md = serializeAssistantMarkdown("Answer.", [
      { title: "Auth", path: "docs/auth.md" },
      { title: "Same", path: "Same" },
    ]);
    expect(md).toContain("Answer.");
    expect(md).toContain("### Sources");
    expect(md).toContain("- Auth (docs/auth.md)");
    expect(md).toContain("- Same");
    expect(md).not.toContain("secret body");
  });

  it("keeps fenced code fences intact", () => {
    const md = serializeAssistantMarkdown("See:\n\n```python\nprint(1)\n```\n");
    expect(md).toContain("```python");
    expect(md).toContain("print(1)");
  });
});

describe("serializeThreadMarkdown", () => {
  it("emits ## You / ## digichat headings and skips empty turns", () => {
    const md = serializeThreadMarkdown([
      { role: "user", content: "What is digichat?" },
      { role: "assistant", content: "" },
      {
        role: "assistant",
        content: "A chat UI.",
        sources: [{ title: "Overview", path: "README.md" }],
      },
    ]);
    expect(md).toContain("## You");
    expect(md).toContain("What is digichat?");
    expect(md).toContain("## digichat");
    expect(md).toContain("A chat UI.");
    expect(md).toContain("- Overview (README.md)");
    expect(md).not.toContain("tool_call");
    expect(md).not.toContain("BYOK");
  });
});

describe("copyMarkdownWithFallback", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    if (typeof document !== "undefined") {
      document.getElementById("dc-copy-fallback")?.remove();
    }
  });

  it("prefers clipboard when writeText resolves", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const result = await copyMarkdownWithFallback("# hi");
    expect(result).toBe("clipboard");
    expect(writeText).toHaveBeenCalledWith("# hi");
  });

  it("falls back to download when clipboard rejects (embed path)", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("blocked"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    // Minimal document stub for downloadMarkdown
    const click = vi.fn();
    const remove = vi.fn();
    const appendChild = vi.fn();
    const createElement = vi.fn((tag: string) => {
      if (tag === "a") {
        return {
          href: "",
          download: "",
          rel: "",
          click,
          remove,
        };
      }
      return {};
    });
    const revoke = vi.fn();
    vi.stubGlobal("URL", {
      createObjectURL: () => "blob:test",
      revokeObjectURL: revoke,
    });
    vi.stubGlobal("document", {
      createElement,
      body: { appendChild },
      getElementById: () => null,
    });
    vi.stubGlobal("Blob", class {
      constructor(public parts: unknown[]) {}
    });

    const result = await copyMarkdownWithFallback("# embed", { filename: "answer.md" });
    expect(result).toBe("download");
    expect(click).toHaveBeenCalled();
    expect(createElement).toHaveBeenCalledWith("a");
  });
});

describe("downloadMarkdown", () => {
  it("throws without a document (node unit env)", () => {
    expect(() => downloadMarkdown("x.md", "y")).toThrow(/document/);
  });
});
