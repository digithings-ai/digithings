"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  // Defer iframe src until after mount so we can read the real parent theme
  // (themeInitScript already flipped data-theme) and avoid a wrong-mode flash.
  const [src, setSrc] = useState("");
  const targetOrigin = useMemo(() => parseOrigin(embedOrigin), [embedOrigin]);
  const configError = targetOrigin
    ? null
    : "Invalid NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN";

  useEffect(() => {
    if (!targetOrigin) return;
    const theme = readParentDocumentTheme();
    themeRef.current = theme;
    setSrc(embedSrc(embedOrigin, embedHost, theme));

    const onThemeAttr = () => {
      const next = readParentDocumentTheme();
      if (next === themeRef.current) return;
      themeRef.current = next;
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
    setShellLoadError(null);

    function onMessage(ev: MessageEvent) {
      if (ev.origin !== targetOrigin) return;
      const data = ev.data as { type?: string } | null;
      if (!data || data.type !== READY) return;
      ready = true;
      embedReadyRef.current = true;
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

  return (
    <div
      className="dc-page"
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        height: "100%",
        minHeight: 0,
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
            color: "color-mix(in srgb, var(--down) 80%, var(--ink))",
          }}
          role="alert"
        >
          <span aria-hidden="true">! </span>
          {shellLoadError}
        </p>
      ) : src ? (
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
