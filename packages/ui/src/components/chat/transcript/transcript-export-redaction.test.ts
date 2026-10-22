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

/** A token shape the redactor matches — a digithings-owned prefix, not a live key. */
const SAMPLE = "digi_live_abcdefghijklmnopqrstuv";

afterEach(() => {
  // Restore the globals first: a test may have stubbed `document` or `window`
  // away, and the cleanup below needs the real ones.
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.replaceChildren();
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

    const result = await copyMarkdownWithFallback(`The overnight key is ${SAMPLE}.`);

    expect(result).toBe("clipboard");
    expect(writeText).toHaveBeenCalledWith("The overnight key is [redacted].");
  });

  it("redacts before the parent-frame copy", async () => {
    // The clipboard is blocked and there is no document to download to, so
    // the payload goes to the parent frame.
    const writeText = vi.fn().mockRejectedValue(new Error("blocked"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const postMessage = vi.fn();
    vi.stubGlobal("window", { parent: { postMessage } });
    vi.stubGlobal("document", undefined);

    const result = await copyMarkdownWithFallback(`The overnight key is ${SAMPLE}.`);

    expect(result).toBe("postMessage");
    expect(postMessage).toHaveBeenCalledTimes(1);
    const payload = postMessage.mock.calls[0]?.[0] as { text: string };
    expect(payload.text).toBe("The overnight key is [redacted].");
  });

  it("redacts before the textarea fallback", async () => {
    // The clipboard is blocked, the download fails and there is no parent
    // frame, so the payload lands in the selectable textarea.
    const writeText = vi.fn().mockRejectedValue(new Error("blocked"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.stubGlobal("window", {});

    const result = await copyMarkdownWithFallback(`The overnight key is ${SAMPLE}.`);

    expect(result).toBe("textarea");
    const field = document.getElementById("dc-copy-fallback") as HTMLTextAreaElement | null;
    expect(field?.value).toBe("The overnight key is [redacted].");
  });

  it("redacts the mailto body before the URL budget is applied", () => {
    const url = buildMailtoUrl("digichat answer", `token=${SAMPLE}`);

    expect(url).not.toContain(SAMPLE);
    expect(url).toContain(encodeURIComponent("[redacted]"));
  });

  it("redacts the mailto subject", () => {
    const url = buildMailtoUrl(`digichat answer ${SAMPLE}`, "hello");

    expect(url).not.toContain(SAMPLE);
    expect(url).toContain(encodeURIComponent("[redacted]"));
  });

  it("keeps a secret that straddles the mailto cut out of the body", () => {
    // The budget cuts inside the secret: the head of the secret must not
    // survive the cut. The padding puts the cut inside the secret's first
    // characters, where the token shape no longer matches the fragment, so a
    // redactor running after the cut would leave it in the URL.
    const body = `${"x".repeat(37)} ${SAMPLE}${"y".repeat(4000)}`;
    const url = buildMailtoUrl("digichat answer", body, { maxEncoded: 120 });

    expect(url).not.toContain("digi_");
    expect(url).not.toContain(SAMPLE);
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

    downloadPlainText("digichat", `The overnight key is ${SAMPLE}.`);

    await vi.waitFor(() => expect(file.text()).toContain("[redacted]"));
    expect(file.text()).not.toContain(SAMPLE);
  });

  it("redacts the minimal HTML export before the file is written", async () => {
    const file = captureWrittenFile();

    downloadHtml("digichat", `The overnight key is ${SAMPLE}.`);

    await vi.waitFor(() => expect(file.text()).toContain("[redacted]"));
    expect(file.text()).not.toContain(SAMPLE);
  });
});
