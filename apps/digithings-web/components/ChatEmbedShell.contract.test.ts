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

  it("covers the cold Container with the shared tool-chain boot until digichat:ready", async () => {
    // Source contract: avoid a white flash on the dark digithings theme (#2093)
    // and keep the cold-start window animated. The shell mounts the shared
    // @digithings/ui tool-chain boot (the loader the embed itself runs), but only after
    // WARMUP_DELAY_MS (warm loads stay flash-free) and only until ready; the
    // iframe is opacity-0 underneath and .dc-chat-frame paints the theme
    // canvas from the first HTML (see globals.css).
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const path = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    expect(src).toContain("BootLabOverlay");
    expect(src).toContain('variant="tooltask"');
    expect(src).toContain("readyEdge={embedReady}");
    expect(src).toContain("WARMUP_DELAY_MS");
    expect(src).toContain("dc-chat-frame");
    expect(src).toContain("digichat:ready");
    expect(src).toContain("opacity: embedReady ? 1 : 0");
    // Curated per-host copy rides into the iframe URL.
    expect(src).toContain("Ask about digithings");
    expect(src).toContain("Ask about Online Compliance Center");
    expect(src).toContain('url.searchParams.set("welcome"');
    expect(src).toContain('url.searchParams.set("suggestions"');
  });

  it("keeps the frame canvas pre-painted under the transparent warmup overlay", async () => {
    // The warmup overlay is transparent (no solid fill) -- the white-flash
    // guard stays on the frame slot: .dc-chat-frame in globals.css paints
    // --chat-frame-canvas (per [data-theme]) from the first HTML, and the
    // iframe's own opacity gate hides the browser-default white underneath.
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const shellPath = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const shellSrc = readFileSync(shellPath, "utf8");
    expect(shellSrc).toContain('className="dc-chat-frame"');
    expect(shellSrc).toContain("BootLabOverlay");
    expect(shellSrc).toContain('background: "transparent"');

    const cssPath = fileURLToPath(new URL("../app/globals.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");
    expect(css).toContain(".dc-chat-frame");
    expect(css).toContain("--chat-frame-canvas");
    expect(css).toContain("@digithings/ui/styles/digichat-boot-loader.css");
  });
});
