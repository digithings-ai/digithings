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

  it("keeps ContainerBootLoader + transparent iframe until digichat:ready", async () => {
    // Source contract: avoid a white flash on the dark digithings theme (#2093).
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const path = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    expect(src).toContain("ContainerBootLoader");
    expect(src).toContain('digichat:ready');
    expect(src).toContain("opacity: embedReady ? 1 : 0");
    expect(src).toContain('backgroundColor: "transparent"');
  });

  it("keeps the boot overlay transparent so .grain/.glow show through while loading", async () => {
    // The overlay used to fill solid `var(--bg)` on the assumption it was the
    // only thing standing between a pre-ready iframe and a white flash -- the
    // iframe's own opacity:0 (asserted above) already does that job. A solid
    // fill there painted a flat rectangle over the page's .grain/.glow the
    // whole time the boot loader was up, then popped to the real background
    // on ready, reading as "a black box that disappears" once digichat loaded.
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const shellPath = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const shellSrc = readFileSync(shellPath, "utf8");

    // The overlay div wrapping ContainerBootLoader: transparent, not var(--bg).
    const overlayBlock = shellSrc.slice(
      shellSrc.indexOf("showBoot ? ("),
      shellSrc.indexOf("<ContainerBootLoader"),
    );
    expect(overlayBlock).toContain('background: "transparent"');
    expect(overlayBlock).not.toContain('background: "var(--bg)"');

    // ContainerBootLoader's own .tl-boot class fills var(--bg) by default (right
    // for its usual standalone-app mode) -- this usage must override it via a
    // scoped className, not by changing the shared component's default.
    expect(shellSrc).toContain('className="dc-embed-boot"');

    const cssPath = fileURLToPath(new URL("../app/globals.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");
    expect(css).toContain(".tl-boot.dc-embed-boot");
    expect(css.match(/\.tl-boot\.dc-embed-boot\s*\{[^}]*background:\s*transparent/)).toBeTruthy();
  });
});
