"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ContainerBootLoader } from "@digithings/web";
import { readAndClearHandoff } from "@/lib/chatHandoff";

const READY = "digichat:ready";
const SEED = "digichat:seed";
/** Keep in sync with digichat `THEME_MESSAGE_TYPE` (`embed-theme-messages.ts`). */
export const THEME = "digichat:theme";
/** Keep in sync with digichat `PARENT_ERROR_MESSAGE_TYPE`. */
export const PARENT_ERROR = "digichat:parent-error";

/** Match digichat READY_TIMEOUT_MS — CF Container cold start can exceed 15s. */
export const EMBED_READY_TIMEOUT_MS = 30_000;

/** Default embed host for digithings.ai/chat (client #0). */
export const DEFAULT_CHAT_EMBED_HOST = "digithings.ai";

/** Virtual first-party host for digithings.ai/chat/occ (client #1). */
export const OCC_CHAT_EMBED_HOST = "occ.digithings.ai";

export type EmbedShellTheme = "light" | "dark";

export type EmbedParentErrorCode = "ready_timeout" | "embed_unloadable";

/** Read parent digithings.ai `[data-theme]` (ThemeProvider / themeInitScript). */
export function readParentDocumentTheme(
  el: { getAttribute(name: string): string | null } = document.documentElement,
): EmbedShellTheme {
  return el.getAttribute("data-theme") === "light" ? "light" : "dark";
}

export function buildEmbedThemeMessage(
  theme: EmbedShellTheme,
  ts = Date.now(),
): { type: typeof THEME; theme: EmbedShellTheme; ts: number } {
  return { type: THEME, theme, ts };
}

/** Parent → embed: surface handshake/load failures inside DigiChatSession. */
export function buildEmbedParentErrorMessage(
  code: EmbedParentErrorCode,
  ts = Date.now(),
): { type: typeof PARENT_ERROR; code: EmbedParentErrorCode; ts: number } {
  return { type: PARENT_ERROR, code, ts };
}

/**
 * Fallback when the iframe never loads (cannot postMessage into digichat).
 * Keep in sync with digichat `formatParentErrorLine("embed_unloadable")`.
 */
export function formatShellLoadErrorLine(): string {
  return (
    "error: digichat embed failed to load — check DIGICHAT_EMBED_ORIGIN and " +
    "Container readiness, then refresh"
  );
}

function parseOrigin(raw: string): string {
  try {
    return new URL(raw).origin;
  } catch {
    return "";
  }
}

function embedSrc(origin: string, embedHost: string, theme: EmbedShellTheme): string {
  const base = origin.replace(/\/$/, "");
  const url = new URL(`${base}/embed`);
  url.searchParams.set("host", embedHost);
  url.searchParams.set("layout", "page");
  url.searchParams.set("theme", theme);
  // Full-page host, not a narrow widget — drop digichat-ui's 1080px reading
  // column so the session fills the shell (see .dc-session--wide).
  url.searchParams.set("wide", "1");
  return url.toString();
}

export type ChatEmbedShellProps = {
  embedOrigin: string;
  /** digichat embed registry host key (default digithings.ai). */
  embedHost?: string;
};

/**
 * digithings.ai chat shell — iframes digichat /embed (digigraph backend).
 * Requires NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN (digichat Container / Worker origin).
 *
 * Theme: reads parent `html[data-theme]` (shared `dt-theme` / ThemeProvider),
 * pins first paint via `?theme=`, then posts `digichat:theme` on ready and on
 * live toggles so the iframe stays in sync without reload.
 *
 * Boot: shows `@digithings/web` ContainerBootLoader on a theme-matched surface
 * until `digichat:ready`. The iframe stays transparent / opacity-0 underneath
 * so a white default document never flashes on the dark digithings theme.
 *
 * Ready failures: posts `digichat:parent-error` into the iframe for in-chat
 * terminal lines (no page banner). If the iframe never loads, shows the same
 * `error: …` line in the iframe slot.
 */
export function ChatEmbedShell({
  embedOrigin,
  embedHost = DEFAULT_CHAT_EMBED_HOST,
}: ChatEmbedShellProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeLoadedRef = useRef(false);
  const embedReadyRef = useRef(false);
  const themeRef = useRef<EmbedShellTheme>("dark");
  /** Only when iframe never loads — cannot deliver parent-error postMessage. */
  const [shellLoadError, setShellLoadError] = useState<string | null>(null);
  const [embedReady, setEmbedReady] = useState(false);
  // Defer iframe src until after mount so we can read the real parent theme
  // (themeInitScript already flipped data-theme) and avoid a wrong-mode flash.
  const [src, setSrc] = useState("");
  const [shellTheme, setShellTheme] = useState<EmbedShellTheme>("dark");
  const targetOrigin = useMemo(() => parseOrigin(embedOrigin), [embedOrigin]);
  const configError = targetOrigin
    ? null
    : "Invalid NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN";

  useEffect(() => {
    if (!targetOrigin) return;
    const theme = readParentDocumentTheme();
    themeRef.current = theme;
    // Defer setState out of the synchronous effect body — react-hooks/set-state-in-effect.
    queueMicrotask(() => {
      setShellTheme(theme);
      setSrc(embedSrc(embedOrigin, embedHost, theme));
    });

    const onThemeAttr = () => {
      const next = readParentDocumentTheme();
      if (next === themeRef.current) return;
      themeRef.current = next;
      setShellTheme(next);
      if (!embedReadyRef.current) return;
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      win.postMessage(buildEmbedThemeMessage(next), targetOrigin);
    };
    const observer = new MutationObserver(onThemeAttr);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, [embedOrigin, embedHost, targetOrigin]);

  useEffect(() => {
    if (!targetOrigin) return;

    let ready = false;
    iframeLoadedRef.current = false;
    embedReadyRef.current = false;
    // Defer setState out of the synchronous effect body — react-hooks/set-state-in-effect.
    queueMicrotask(() => {
      setShellLoadError(null);
      setEmbedReady(false);
    });

    function onMessage(ev: MessageEvent) {
      if (ev.origin !== targetOrigin) return;
      const data = ev.data as { type?: string } | null;
      if (!data || data.type !== READY) return;
      ready = true;
      embedReadyRef.current = true;
      setEmbedReady(true);
      setShellLoadError(null);
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      // Always sync theme on ready (covers cold load + late handshake).
      win.postMessage(buildEmbedThemeMessage(themeRef.current), targetOrigin);
      const handoff = readAndClearHandoff();
      if (!handoff || (!handoff.messages.length && !handoff.pending)) return;
      win.postMessage(
        {
          type: SEED,
          messages: handoff.messages,
          pending: handoff.pending ?? null,
          ts: Date.now(),
        },
        targetOrigin,
      );
    }

    window.addEventListener("message", onMessage);
    const t = window.setTimeout(() => {
      if (ready) return;
      const win = iframeRef.current?.contentWindow;
      if (iframeLoadedRef.current && win) {
        // Iframe painted but never said ready — surface inside digichat transcript.
        win.postMessage(buildEmbedParentErrorMessage("ready_timeout"), targetOrigin);
        // Reveal the iframe so the in-chat error line is visible.
        setEmbedReady(true);
        return;
      }
      // No browsing context to post into — terminal line in the iframe slot.
      setShellLoadError(formatShellLoadErrorLine());
    }, EMBED_READY_TIMEOUT_MS);
    return () => {
      window.removeEventListener("message", onMessage);
      window.clearTimeout(t);
    };
  }, [targetOrigin]);

  if (configError) {
    return (
      <p className="dc-page" style={{ padding: "2rem" }}>
        {configError}
      </p>
    );
  }

  const showBoot = !shellLoadError && !embedReady;

  return (
    <div
      // Not className="dc-page": that class (session.css) is digichat-ui's own
      // standalone-page padding/min-height rule, meant for a page with no other
      // chrome around it. The parent <main> here (chat/page.tsx, chat/occ/page.tsx)
      // already pads for the fixed nav, so stacking .dc-page's own nav-clearing
      // padding on top doubled it. Nothing else in the codebase reads .dc-page —
      // it was never actually shared, just misapplied here.
      data-theme={shellTheme}
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        height: "100%",
        minHeight: 0,
        position: "relative",
        // The proportioned-page look (gutters, breathing room off the floor)
        // belongs to this host page, not the guest iframe — the iframe just
        // fills whatever box it's given, edge-to-edge (digichat's own
        // .dc-session--wide does the same: no internal cap once `wide=1`).
        // Sizing it here instead of inside digichat also means it responds
        // to this page's own breakpoints, not a copy of them maintained on
        // the other side of the iframe boundary.
        width: "100%",
        maxWidth: "min(1280px, 90vw)",
        marginInline: "auto",
        // Symmetric with paddingBottom: the parent <main> no longer reserves
        // --dq-nav-h up top (DtNav is autoHide="hover" now, overlaying rather
        // than pushing content down), so without this the chat sat flush
        // against the very top while keeping its bottom gap — lopsided.
        paddingTop: "clamp(0.75rem, 2.5vw, 1.75rem)",
        paddingBottom: "clamp(0.75rem, 2.5vw, 1.75rem)",
        // Transparent, not var(--bg): the page's fixed .grain/.glow layers (site.css,
        // z-index 0) sit behind this shell, and an opaque fill here paints a visible
        // rectangle over them. The boot overlay below is transparent for the same
        // reason (see its own comment) -- the iframe's opacity:0 already hides any
        // browser-default white pre-ready, so nothing here needs a solid fill.
        background: "transparent",
        colorScheme: shellTheme,
      }}
    >
      {shellLoadError ? (
        <p
          className="font-mono"
          style={{
            flex: 1,
            margin: 0,
            padding: "0.85rem 0.75rem",
            fontSize: "0.8rem",
            color: "color-mix(in srgb, var(--danger) 80%, var(--ink))",
          }}
          role="alert"
        >
          <span aria-hidden="true">! </span>
          {shellLoadError}
        </p>
      ) : null}

      {showBoot ? (
        <div
          aria-busy="true"
          aria-live="polite"
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 1,
            // Transparent, not var(--bg) -- same reasoning as the shell div above.
            // This used to fill solid on the (mistaken) assumption that it was the
            // only thing standing between a pre-ready iframe and a flash of
            // browser-default white, but the iframe's own opacity:0 (below) already
            // does that job. A solid fill here just painted a flat, textureless
            // rectangle over the page's .grain/.glow the whole time this was up,
            // then popped to the real (transparent) background on ready -- visible
            // as a "black box that disappears" once digichat loaded.
            background: "transparent",
          }}
        >
          <ContainerBootLoader
            title="digichat"
            note="waking the embed · first paint after digichat:ready"
            fullscreen={false}
            // ContainerBootLoader's own .tl-boot class fills var(--bg) by default --
            // right for its usual mode (a plain app with nothing behind it), wrong
            // here where .grain/.glow should show through. Scoped override below,
            // not a change to the shared component or its default styling.
            className="dc-embed-boot"
          />
        </div>
      ) : null}

      {src && !shellLoadError ? (
        <iframe
          ref={iframeRef}
          title="digichat"
          src={src}
          style={{
            flex: 1,
            width: "100%",
            border: 0,
            minHeight: 0,
            height: "100%",
            // Transparent until ready — default iframe white never paints over --bg.
            backgroundColor: "transparent",
            colorScheme: shellTheme,
            opacity: embedReady ? 1 : 0,
            position: "relative",
            zIndex: 0,
          }}
          allow="clipboard-write"
          onLoad={() => {
            iframeLoadedRef.current = true;
            setShellLoadError(null);
          }}
        />
      ) : null}
    </div>
  );
}
