import { describe, it, expect } from "vitest";
import {
  DEFAULT_CHAT_EMBED_HOST,
  EMBED_READY_TIMEOUT_MS,
  OCC_CHAT_EMBED_HOST,
  PARENT_ERROR,
  THEME,
  buildEmbedParentErrorMessage,
  buildEmbedThemeMessage,
  formatShellLoadErrorLine,
  readParentDocumentTheme,
} from "@/components/ChatEmbedShell";

describe("ChatEmbedShell contracts", () => {
  it("keeps OCC as a virtual host distinct from the digithings parent", () => {
    expect(DEFAULT_CHAT_EMBED_HOST).toBe("digithings.ai");
    expect(OCC_CHAT_EMBED_HOST).toBe("occ.digithings.ai");
    expect(OCC_CHAT_EMBED_HOST).not.toBe(DEFAULT_CHAT_EMBED_HOST);
  });

  it("allows cold-start before treating a missing ready as a load failure", () => {
    expect(EMBED_READY_TIMEOUT_MS).toBeGreaterThanOrEqual(30_000);
  });

  it("posts digichat:theme with light|dark only", () => {
    expect(THEME).toBe("digichat:theme");
    expect(buildEmbedThemeMessage("light")).toEqual({
      type: "digichat:theme",
      theme: "light",
      ts: expect.any(Number),
    });
    expect(buildEmbedThemeMessage("dark", 42)).toEqual({
      type: "digichat:theme",
      theme: "dark",
      ts: 42,
    });
  });

  it("posts digichat:parent-error for in-chat handshake failures", () => {
    expect(PARENT_ERROR).toBe("digichat:parent-error");
    expect(buildEmbedParentErrorMessage("ready_timeout", 99)).toEqual({
      type: "digichat:parent-error",
      code: "ready_timeout",
      ts: 99,
    });
    expect(buildEmbedParentErrorMessage("embed_unloadable").code).toBe(
      "embed_unloadable",
    );
  });

  it("formats shell load fallback without tunnel/DIGICHAT_EMBED_HOSTS copy", () => {
    const line = formatShellLoadErrorLine();
    expect(line.startsWith("error: ")).toBe(true);
    expect(line).toContain("DIGICHAT_EMBED_ORIGIN");
    expect(line).toContain("Container");
    expect(line).not.toContain("tunnel");
    expect(line).not.toContain("DIGICHAT_EMBED_HOSTS");
  });

  it("reads parent html data-theme as light or dark", () => {
    expect(readParentDocumentTheme({ getAttribute: () => "light" })).toBe("light");
    expect(readParentDocumentTheme({ getAttribute: () => "dark" })).toBe("dark");
    expect(readParentDocumentTheme({ getAttribute: () => null })).toBe("dark");
  });

  it("keeps the frame canvas pre-painted and the in-app boot as the only loader until digichat:ready settles", async () => {
    // Source contract: avoid a white flash on the dark digithings theme (#2093).
    // The shell no longer mounts its own boot overlay -- digichat's in-app boot
    // chain is the only loader, and the frame slot paints the theme canvas from
    // the first HTML via .dc-chat-frame (see globals.css).
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const path = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    expect(src).toContain("dc-chat-frame");
    expect(src).toContain("digichat:ready");
    expect(src).not.toContain("DigichatBootLoader");
    // Curated per-host copy rides into the iframe URL.
    expect(src).toContain("Ask about digithings");
    expect(src).toContain("Ask about Online Compliance Center");
    expect(src).toContain('url.searchParams.set("welcome"');
    expect(src).toContain('url.searchParams.set("suggestions"');
  });

  it("paints the frame canvas pre-paint instead of mounting a solid boot overlay", async () => {
    // The old shell overlay is gone -- digichat boots inside the frame now. The
    // white-flash guard moved to the frame slot: .dc-chat-frame in globals.css
    // paints --chat-frame-canvas (per [data-theme]) from the first HTML, so the
    // pre-ready frame is never a browser-default white rectangle.
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const shellPath = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const shellSrc = readFileSync(shellPath, "utf8");
    expect(shellSrc).toContain('className="dc-chat-frame"');
    expect(shellSrc).not.toContain("DigichatBootLoader");

    const cssPath = fileURLToPath(new URL("../app/globals.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");
    expect(css).toContain(".dc-chat-frame");
    expect(css).toContain("--chat-frame-canvas");
    expect(css).toContain("@digithings/ui/styles/digichat-boot-loader.css");
  });
});
