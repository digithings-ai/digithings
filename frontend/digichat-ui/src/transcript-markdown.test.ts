/**
 * Serializer + embed fallback for turn / thread markdown export (#3465).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildMailtoUrl,
  buildThreadMailto,
  copyMarkdownWithFallback,
  downloadMarkdown,
  markdownToHtmlDocument,
  markdownToPlainText,
  openMailtoWithFallback,
  printTranscriptWithFallback,
  serializeAssistantMarkdown,
  serializeThreadMarkdown,
  truncateForMailto,
  MAILTO_MAX_ENCODED_LEN,
  MAILTO_TRUNCATION_NOTE,
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
          setAttribute: vi.fn(),
          style: {},
          focus: vi.fn(),
          select: vi.fn(),
        };
      }
      return {
        id: "",
        value: "",
        setAttribute: vi.fn(),
        style: {},
        focus: vi.fn(),
        select: vi.fn(),
        readOnly: false,
      };
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
    vi.stubGlobal(
      "Blob",
      class MockBlob {
        // eslint-disable-next-line @typescript-eslint/no-useless-constructor -- mirror Blob arity for callers
        constructor(_parts: unknown[], _opts?: unknown) {}
      },
    );
    // Run deferred revoke synchronously so the stub stays live for the call.
    vi.stubGlobal("setTimeout", ((fn: () => void) => {
      fn();
      return 0;
    }) as unknown as typeof setTimeout);

    const result = await copyMarkdownWithFallback("# embed", { filename: "answer.md" });
    expect(result).toBe("download");
    expect(click).toHaveBeenCalled();
    expect(createElement).toHaveBeenCalledWith("a");
    expect(revoke).toHaveBeenCalledWith("blob:test");
  });
});

describe("downloadMarkdown", () => {
  it("throws without a document (node unit env)", () => {
    expect(() => downloadMarkdown("x.md", "y")).toThrow(/document/);
  });
});

describe("truncateForMailto (#3510)", () => {
  it("passes short bodies through untouched", () => {
    expect(truncateForMailto("Hello world")).toEqual({ text: "Hello world", truncated: false });
  });

  it("cuts long bodies to the URL budget and appends the truncation note", () => {
    const result = truncateForMailto("x".repeat(5000));
    expect(result.truncated).toBe(true);
    expect(result.text).toContain(MAILTO_TRUNCATION_NOTE);
    expect(encodeURIComponent(result.text).length).toBeLessThanOrEqual(
      MAILTO_MAX_ENCODED_LEN,
    );
  });

  it("measures multi-byte chars after encoding, not by length", () => {
    const result = truncateForMailto("€".repeat(2000));
    expect(result.truncated).toBe(true);
    expect(encodeURIComponent(result.text).length).toBeLessThanOrEqual(
      MAILTO_MAX_ENCODED_LEN,
    );
  });
});

describe("buildMailtoUrl (#3510)", () => {
  it("encodes a short subject + body with no network", () => {
    const url = buildMailtoUrl("digichat answer", "Hello & goodbye");
    expect(url.startsWith("mailto:?subject=digichat%20answer&body=")).toBe(true);
    expect(url).toContain(encodeURIComponent("Hello & goodbye"));
  });

  it("thread mailto stays truncation-safe and keeps the .md fallback note", () => {
    const url = buildThreadMailto("y".repeat(4000));
    expect(url).toContain(encodeURIComponent(MAILTO_TRUNCATION_NOTE));
    const bodyParam = url.split("&body=")[1] ?? "";
    expect(bodyParam.length).toBeLessThanOrEqual(MAILTO_MAX_ENCODED_LEN);
  });
});

describe("markdownToPlainText / markdownToHtmlDocument (#3510)", () => {
  it("strips fence delimiters but keeps code content", () => {
    const txt = markdownToPlainText("See:\n\n```python\nprint(1)\n```\n");
    expect(txt).not.toContain("```");
    expect(txt).toContain("print(1)");
  });

  it("wraps escaped markdown in a minimal html doc without a renderer", () => {
    const html = markdownToHtmlDocument("# hi <b>", "digichat transcript");
    expect(html).toContain("<pre>");
    expect(html).toContain("&lt;b&gt;");
    expect(html).not.toContain("<b>");
  });
});

describe("printTranscriptWithFallback / openMailtoWithFallback (#3510)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("calls window.print when available", () => {
    const print = vi.fn();
    vi.stubGlobal("window", { print });
    expect(printTranscriptWithFallback()).toBe("print");
    expect(print).toHaveBeenCalled();
  });

  it("falls back to download when print is unavailable", () => {
    vi.stubGlobal("window", undefined);
    expect(printTranscriptWithFallback()).toBe("download");
  });

  it("preferDownload skips print even when window.print exists (embed)", () => {
    const print = vi.fn();
    const click = vi.fn();
    const anchor = { href: "", download: "", rel: "", click, remove: vi.fn() };
    vi.stubGlobal("window", { print });
    vi.stubGlobal("document", {
      createElement: () => anchor,
      body: { appendChild: vi.fn() },
    });
    vi.stubGlobal("URL", {
      createObjectURL: () => "blob:test",
      revokeObjectURL: vi.fn(),
    });
    expect(
      printTranscriptWithFallback({
        preferDownload: true,
        fallbackMarkdown: "# thread",
        fallbackFilename: "digichat-thread.md",
      }),
    ).toBe("download");
    expect(print).not.toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
  });

  it("opens mailto via an anchor click without network", () => {
    const click = vi.fn();
    const anchor = { href: "", rel: "", click, remove: vi.fn() };
    vi.stubGlobal("document", {
      createElement: () => anchor,
      body: { appendChild: vi.fn() },
    });
    const url = buildMailtoUrl("digichat answer", "Hi");
    expect(openMailtoWithFallback(url)).toBe("mailto");
    expect(anchor.href).toBe(url);
    expect(click).toHaveBeenCalled();
  });

  it("rejects non-mailto URLs and downloads fallback instead", () => {
    const click = vi.fn();
    const anchor = { href: "", download: "", rel: "", click, remove: vi.fn() };
    vi.stubGlobal("document", {
      createElement: () => anchor,
      body: { appendChild: vi.fn() },
    });
    vi.stubGlobal("URL", {
      createObjectURL: () => "blob:test",
      revokeObjectURL: vi.fn(),
    });
    expect(
      openMailtoWithFallback("https://evil.example/", {
        fallbackMarkdown: "safe",
        fallbackFilename: "digichat-answer.md",
      }),
    ).toBe("download");
    expect(anchor.href).not.toBe("https://evil.example/");
    expect(click).toHaveBeenCalled();
  });

  it("preferDownload skips mailto navigation (embed)", () => {
    const click = vi.fn();
    const anchor = { href: "", download: "", rel: "", click, remove: vi.fn() };
    vi.stubGlobal("document", {
      createElement: () => anchor,
      body: { appendChild: vi.fn() },
    });
    vi.stubGlobal("URL", {
      createObjectURL: () => "blob:test",
      revokeObjectURL: vi.fn(),
    });
    const url = buildMailtoUrl("digichat answer", "Hi");
    expect(
      openMailtoWithFallback(url, {
        preferDownload: true,
        fallbackMarkdown: "Hi",
        fallbackFilename: "digichat-answer.md",
      }),
    ).toBe("download");
    expect(anchor.href).not.toBe(url);
    expect(click).toHaveBeenCalled();
  });
});
