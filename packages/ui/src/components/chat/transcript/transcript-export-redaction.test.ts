/**
 * @vitest-environment happy-dom
 *
 * Every digichat export path runs its payload through the shared redactor
 * (`packages/ui/src/replay/redact.ts`): the clipboard copy, the `mailto:`
 * body, the `.txt` export and the minimal-HTML export. One mocked test per
 * path (DIG-5057).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildMailtoUrl,
  copyMarkdownWithFallback,
  downloadHtml,
  downloadPlainText,
} from "./transcript-markdown";

/** A token shape the redactor matches. */
const SECRET = "sk-ant-abcdefghijklmnopqrst";

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Capture the text of the file the export writes. */
function captureWrittenFile(): { text: () => string } {
  const written = { text: "" };
  vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
    void (blob as Blob).text().then((text) => {
      written.text = text;
    });
    return "blob:export";
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  return { text: () => written.text };
}

describe("export paths redact the payload", () => {
  it("redacts before the clipboard copy", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    const result = await copyMarkdownWithFallback(`The overnight key is ${SECRET}.`);

    expect(result).toBe("clipboard");
    expect(writeText).toHaveBeenCalledWith("The overnight key is [redacted].");
  });

  it("redacts the mailto body before the URL budget is applied", () => {
    const url = buildMailtoUrl("digichat answer", `token=${SECRET}`);

    expect(url).not.toContain(SECRET);
    expect(url).toContain(encodeURIComponent("[redacted]"));
  });

  it("keeps a secret that straddles the mailto cut out of the body", () => {
    // The budget cuts inside the secret: no part of it may survive the cut.
    const body = `${"x".repeat(20)} ${SECRET}${"y".repeat(4000)}`;
    const url = buildMailtoUrl("digichat answer", body, { maxEncoded: 120 });

    expect(url).not.toContain("sk-an");
    expect(url).not.toContain("abcdefghij");
  });

  it("never leaves half a redaction marker in the mailto body", () => {
    // The cut lands inside the marker: the partial marker is dropped
    // rather than written out as "[redac".
    const body = `${"x".repeat(20)}[redacted]${"y".repeat(4000)}`;
    const url = buildMailtoUrl("digichat answer", body, { maxEncoded: 105 });

    expect(url).not.toContain("%5Bredac");
    expect(url).not.toContain("[redac");
  });

  it("redacts the .txt export before the file is written", async () => {
    const file = captureWrittenFile();

    downloadPlainText("digichat", `The overnight key is ${SECRET}.`);

    await vi.waitFor(() => expect(file.text()).toContain("[redacted]"));
    expect(file.text()).not.toContain(SECRET);
  });

  it("redacts the minimal HTML export before the file is written", async () => {
    const file = captureWrittenFile();

    downloadHtml("digichat", `The overnight key is ${SECRET}.`);

    await vi.waitFor(() => expect(file.text()).toContain("[redacted]"));
    expect(file.text()).not.toContain(SECRET);
  });
});
