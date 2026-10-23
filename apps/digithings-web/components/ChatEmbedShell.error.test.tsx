import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  EMBED_LOAD_ERROR_RETRY,
  EMBED_LOAD_ERROR_TITLE,
  EMBED_SHELL_CLASS,
  EmbedLoadErrorCard,
  embedDocumentFailed,
} from "@/components/ChatEmbedShell";

/**
 * Failed embed (the container's 500, a 503 while the slot is busy, a frame
 * that never loads): the shell shows the in-chat error notice centered in the
 * chat slot, with visitor-facing copy and the Retry action. Mocked only — no
 * network, no container, no model.
 */
describe("ChatEmbedShell load failure", () => {
  const html = renderToStaticMarkup(createElement(EmbedLoadErrorCard, { onRetry: vi.fn() }));

  it("reuses the in-chat error notice, centered", () => {
    expect(html).toContain('data-slot="chat-notice"');
    expect(html).toContain('data-tone="error"');
    expect(html).toContain("aui-chat-notice");
    expect(html).toContain('role="alert"');
    // Same skin scope as the transcript, so the same notice styling applies.
    expect(html).toContain('data-thread-skin="digichat"');
    expect(html).toMatch(/align-items:center/);
    expect(html).toMatch(/justify-content:center/);
  });

  it("carries the Retry action of the in-chat card", () => {
    expect(html).toContain("aui-message-error-retry");
    expect(html).toContain(`>${EMBED_LOAD_ERROR_RETRY}</button>`);
  });

  it("shows user-facing copy only", () => {
    expect(html).toContain(EMBED_LOAD_ERROR_TITLE);
    for (const leak of [
      "DIGICHAT_EMBED_ORIGIN",
      "NEXT_PUBLIC",
      "Container",
      "digichat embed failed to load",
      "https://",
      "localhost",
    ]) {
      expect(html).not.toContain(leak);
    }
  });

  it("treats a same-origin frame without the embed shell as failed", () => {
    const doc = (shell: boolean, url = "https://digithings.ai/embed?host=digithings.ai") =>
      ({
        URL: url,
        querySelector: (sel: string) => (shell && sel === ".dc-embed-shell" ? {} : null),
      }) as unknown as Document;
    expect(embedDocumentFailed({ contentDocument: doc(false) })).toBe(true);
    expect(embedDocumentFailed({ contentDocument: doc(true) })).toBe(false);
    // Not yet navigated, or cross-origin (contentDocument null): unknown, so
    // the ready timeout decides.
    expect(embedDocumentFailed({ contentDocument: doc(false, "about:blank") })).toBe(false);
    expect(embedDocumentFailed({ contentDocument: null })).toBe(false);
    expect(embedDocumentFailed(null)).toBe(false);
  });

  it("probes for the class the digichat embed really renders", async () => {
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const embedShell = readFileSync(
      fileURLToPath(
        new URL("../../digichat/src/app/(digichat)/embed-route-shell.tsx", import.meta.url),
      ),
      "utf8",
    );
    expect(embedShell).toMatch(new RegExp(`className="${EMBED_SHELL_CLASS}[ "]`));
  });

  it("wires Retry to reload the embed in place", async () => {
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const src = readFileSync(
      fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url)),
      "utf8",
    );
    expect(src).toContain("<EmbedLoadErrorCard onRetry={retryEmbed} />");
    expect(src).toContain("key={attempt}");
    expect(src).toContain("setAttempt((n) => n + 1)");
    expect(src).toContain("}, [targetOrigin, attempt]);");
    // The raw terminal line is gone from the rendered tree.
    expect(src).not.toContain("{shellLoadError}");
  });
});
