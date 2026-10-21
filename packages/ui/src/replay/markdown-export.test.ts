/**
 * @vitest-environment happy-dom
 *
 * `/export`, `/export md`, and the message menu's markdown download share
 * `downloadMarkdown`. The file goes through the same string redactor as HTML.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { downloadMarkdown } from "../components/chat/transcript/transcript-markdown";

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("markdown export redaction", () => {
  it("redacts token shapes before the file is saved", async () => {
    const secret = "sk-ant-abcdefghijklmnopqrst";
    const invite = "ab".repeat(24);
    let captured = "";
    vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
      void (blob as Blob).text().then((text) => {
        captured = text;
      });
      return "blob:markdown";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    downloadMarkdown("digichat.md", `The overnight book is flat.\n${secret}\n${invite}`);
    await vi.waitFor(() => expect(captured).toContain("[redacted]"));
    expect(captured).toContain("The overnight book is flat.");
    expect(captured).not.toContain(secret);
    expect(captured).not.toContain(invite);
  });
});
