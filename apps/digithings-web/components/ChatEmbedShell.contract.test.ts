import { describe, it, expect } from "vitest";
import {
  DEFAULT_CHAT_EMBED_HOST,
  EMBED_READY_TIMEOUT_MS,
  OCC_CHAT_EMBED_HOST,
  PARENT_ERROR,
  THEME,
  buildEmbedParentErrorMessage,
  buildEmbedThemeMessage,
  formatShellLoadDiagnostic,
  readParentDocumentPalette,
  readParentDocumentTheme,
  readPrivateMode,
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

  it("forwards private mode only for an exact 1, for any tenant", () => {
    expect(readPrivateMode("?private=1")).toBe(true);
    expect(readPrivateMode("?private=0")).toBe(false);
    expect(readPrivateMode("?private=true")).toBe(false);
    expect(readPrivateMode("?private=")).toBe(false);
    expect(readPrivateMode("?wide=1")).toBe(false);
    expect(readPrivateMode("")).toBe(false);
    expect(readPrivateMode(undefined)).toBe(false);
  });

  it("posts digichat:theme with light|dark and an optional palette", () => {
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

  it("forwards only a known parent palette on the theme message", () => {
    const attr = (v: string | null) => ({ getAttribute: () => v });
    expect(readParentDocumentPalette(attr("dracula"))).toBe("dracula");
    expect(readParentDocumentPalette(attr(" Nord "))).toBe("nord");
    expect(readParentDocumentPalette(attr("default"))).toBeUndefined();
    expect(readParentDocumentPalette(attr("nope"))).toBeUndefined();
    expect(readParentDocumentPalette(attr(null))).toBeUndefined();
    expect(buildEmbedThemeMessage("light", 1, "dracula")).toEqual({
      type: THEME,
      theme: "light",
      ts: 1,
      palette: "dracula",
    });
    expect(buildEmbedThemeMessage("dark", 1)).toEqual({ type: THEME, theme: "dark", ts: 1 });
    expect("palette" in buildEmbedThemeMessage("dark", 1)).toBe(false);
  });

  it("posts digichat:parent-error for in-chat handshake failures", () => {
    expect(PARENT_ERROR).toBe("digichat:parent-error");
    expect(buildEmbedParentErrorMessage("ready_timeout", 99)).toEqual({
      type: "digichat:parent-error",
      code: "ready_timeout",
      ts: 99,
    });
    expect(buildEmbedParentErrorMessage("embed_unloadable").code).toBe("embed_unloadable");
  });

  it("keeps the operator diagnostic for the dev console only", async () => {
    const line = formatShellLoadDiagnostic("test");
    expect(line).toContain("DIGICHAT_EMBED_ORIGIN");
    expect(line).not.toContain("tunnel");
    // Logged, never rendered: the only caller is the console helper, and it
    // is silent in production builds.
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const src = readFileSync(
      fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url)),
      "utf8",
    );
    expect(src.split("formatShellLoadDiagnostic(").length - 1).toBe(2); // definition + console.error
    expect(src).toContain('if (process.env.NODE_ENV === "production") return;');
    expect(src).toContain("console.error(formatShellLoadDiagnostic(reason))");
  });

  it("reads parent html data-theme as light or dark", () => {
    expect(readParentDocumentTheme({ getAttribute: () => "light" })).toBe("light");
    expect(readParentDocumentTheme({ getAttribute: () => "dark" })).toBe("dark");
    expect(readParentDocumentTheme({ getAttribute: () => null })).toBe("dark");
  });

  it("posts digichat:theme on a live toggle instead of rebuilding iframe src", async () => {
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const path = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    const start = src.indexOf("const onThemeAttr");
    const end = src.indexOf("const observer", start);
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const handler = src.slice(start, end);
    expect(handler).not.toContain("setSrc");
    expect(handler).toContain("postMessage");
    expect(handler).toContain("buildEmbedThemeMessage");
  });

  it("covers the cold Container with the digichat hero banner until digichat:ready", async () => {
    // Source contract: avoid a white flash on the dark digithings theme (#2093)
    // and keep the cold-start window animated. One cover for every surface —
    // /chat, /chat/occ, the landing pop-up and the host panels: the digichat
    // hero banner's LOADING pass, the same animation digichat paints itself.
    // The old BootLabOverlay tool-chain rows are gone on purpose; they
    // simulated tool work the visitor never started and made the OCC chat
    // differ from the digichat chat. Mounted only after WARMUP_DELAY_MS (warm
    // loads stay flash-free) and only until ready; the iframe is opacity-0
    // underneath and .dc-chat-frame paints the theme canvas from the first
    // HTML (see globals.css).
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const path = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    // No caller can reach the old tool-call rows: the variant, the component
    // and the switch that chose between them are all gone.
    expect(src).not.toContain("BootLabOverlay");
    expect(src).not.toContain("tooltask");
    expect(src).not.toContain("warmupLoader");
    // Reveal waits on the iframe handshake AND the shared service warm-up.
    // Same gate for the landing pop-up, /chat, and /chat/occ.
    expect(src).toContain("aria-busy={!revealed}");
    expect(src).toContain("waitForServices");
    expect(src).toContain("const revealed = (embedReady && servicesReady) || forceReveal");
    expect(src).toContain(`signalDigichatBootStep("services")`);
    expect(src).toContain("WARMUP_DELAY_MS");
    expect(src).toContain("dc-chat-frame");
    expect(src).toContain("digichat:ready");
    expect(src).toContain("opacity: revealed ? 1 : 0");

    // The banner is the cover, unconditionally, and the screen-reader line with
    // it. The error card is a sibling of this region (see EmbedLoadErrorCard
    // below), so removing the tool-chain branch orphaned nothing.
    expect(src).toContain('from "@digithings/hero-banner/web"');
    expect(src).toContain('from "@digithings/hero-banner/definitions"');
    expect(src).toContain("<HeroBanner def={DIGICHAT} replayLoading />");
    expect(src).toContain("min(560px, 72vw)");
    expect(src).toContain("Loading chat…");
    expect(src).toContain("<EmbedLoadErrorCard onRetry={retryEmbed} />");

    const pageShellSrc = readFileSync(
      fileURLToPath(new URL("./ChatPageShell.tsx", import.meta.url)),
      "utf8",
    );
    // The full-page route no longer asks for the banner — it is the default.
    expect(pageShellSrc).not.toContain("warmupLoader");
    // Curated per-host copy rides into the iframe URL. The strings themselves
    // live in lib/embedCopy.ts now, so the landing page's FAQ band can mount the
    // same conversation with the same welcome — assert both halves: the URL
    // wiring here, and that the shell still reads its copy from the shared
    // record rather than keeping a private copy that could drift.
    expect(src).toContain('url.searchParams.set("welcome"');
    expect(src).toContain('url.searchParams.set("suggestions"');
    expect(src).toContain('from "@/lib/embedCopy"');

    const copyPath = fileURLToPath(new URL("../lib/embedCopy.ts", import.meta.url));
    const copy = readFileSync(copyPath, "utf8");
    expect(copy).toContain("Ask about digithings");
    expect(copy).toContain("Ask about Online Compliance Center");
  });

  it("forwards the OCC invite key from the parent URL to the embed", async () => {
    // DIG-1210. The barrier is a bearer capability in the parent URL, handed
    // straight to digichat under the one name it already enforces (`token=`).
    // Source contract: the key must be read from window.location inside the
    // mount effect, never during render — this app is output: "export", so the
    // shipped HTML is one static artifact every visitor shares.
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const path = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");

    expect(src).toContain('from "@/lib/inviteToken"');
    expect(src).toContain("readInviteToken(window.location.search)");
    expect(src).toContain('url.searchParams.set("token", inviteToken)');

    // Read behind the route's opt-in, never unconditionally: /chat must not
    // pick up a stray ?token= and hand it to a tenant that never asked for one.
    expect(src).toContain("acceptsInviteToken");
    const readIndex = src.indexOf("readInviteToken(window.location.search)");
    // Formatting-agnostic: Prettier may keep the guard ternary on one line.
    const guardIndex = src.search(/acceptsInviteToken\s*\?\s*readInviteToken/);
    expect(guardIndex).toBeGreaterThan(-1);
    expect(guardIndex).toBeLessThan(readIndex);

    // Rebuilt only when something is actually missing. An invite link needs one
    // extra src swap on hydration (the exported first paint had no key); every
    // other visitor's src must be left alone.
    expect(src).toContain("missingToken");
    expect(src).toContain('!current.includes("token=")');
  });

  it("serves OCC from the app, not a Pages shell (2026-10-27 consolidation)", async () => {
    const { existsSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    // The OCC shell and its Pages twin gate are gone: /chat/occ is the app's
    // own embed route, gated once at the Worker and proxied to the container.
    // A reappearing Pages copy would reintroduce the second secret and the
    // second deploy surface this change removed.
    expect(
      existsSync(fileURLToPath(new URL("../app/chat/occ/page.tsx", import.meta.url))),
    ).toBe(false);
    expect(
      existsSync(fileURLToPath(new URL("../functions/chat/occ/[[path]].ts", import.meta.url))),
    ).toBe(false);
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
    // First embed request carries the parent palette, not only light/dark.
    expect(shellSrc).toContain("EMBED_FRAME_THEME_SCRIPT");
    expect(shellSrc).toContain("url.searchParams.set('palette',palette)");
    // The transparent overlay is the banner cover now, not the tool-chain rows.
    expect(shellSrc).toContain("<HeroBanner def={DIGICHAT} replayLoading />");
    expect(shellSrc).toContain('background: "transparent"');

    const cssPath = fileURLToPath(new URL("../app/globals.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");
    expect(css).toContain(".dc-chat-frame");
    expect(css).toContain("--chat-frame-canvas");
    expect(css).toContain("@digithings/ui/styles/digichat-boot-loader.css");
  });

  it("strips the invite key from the address bar right after reading it (DIG-1437)", async () => {
    // The key must not survive in browser history or in the visible address
    // bar. It is read client-side inside the mount effect, so that is the only
    // place the rewrite can happen; doing it during render would put the key
    // back into the exported HTML this app ships as one shared artifact.
    const { readFileSync } = await import("node:fs");
    const { fileURLToPath } = await import("node:url");
    const path = fileURLToPath(new URL("./ChatEmbedShell.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");

    expect(src).toContain("stripInviteTokenFromUrl");

    // One call site, and it is the rewrite. A second would mean the key is
    // being scrubbed twice, which is churn, not defence.
    expect(src.split("window.history.replaceState").length - 1).toBe(1);

    // Gated on the route opt-in and on a non-empty key, so an ordinary /chat
    // visit never touches history.
    const readIndex = src.indexOf("readInviteToken(window.location.search)");
    const stripIndex = src.indexOf("stripInviteTokenFromUrl(window.location.href)");
    const guardIndex = src.search(/acceptsInviteToken\s*\?\s*readInviteToken/);
    expect(guardIndex).toBeGreaterThan(-1);
    expect(stripIndex).toBeGreaterThan(readIndex);
    expect(stripIndex).toBeGreaterThan(-1);
    expect(src).toContain("token ? stripInviteTokenFromUrl");

    // The token stays in the effect's local state for the session and nowhere
    // else — no store, no cookie, no sessionStorage. These match a USE
    // (sessionStorage.setItem, document.cookie =), not the bare word: a
    // guard on the bare name fires on this comment and on any prose that
    // documents the rule, which is a test that cannot fail for its reason.
    expect(src).not.toMatch(/sessionStorage\s*\.\s*(set|get|remove|clear)Item\s*\(/);
    expect(src).not.toMatch(/localStorage\s*\.\s*(set|get|remove|clear)Item\s*\(/);
    expect(src).not.toContain("setItem(");
    expect(src).not.toMatch(/document\s*\.\s*cookie\s*=[^=]/);
  });
});
