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

/**
 * Curated first-paint copy per host: the boot loader types it while the
 * container wakes, and the same strings ride the iframe URL so the ready hero
 * matches the loader it replaces. Keep every example a single line — the
 * chips render one row each.
 */
export const EMBED_SHELL_COPY: Record<
  string,
  { welcome: string; suggestions: string[] }
> = {
  [DEFAULT_CHAT_EMBED_HOST]: {
    welcome: "Ask about digithings",
    suggestions: [
      "What is digigraph?",
      "Search the docs for NautilusTrader",
      "How do I run the stack locally?",
      "Summarize the digithings architecture",
    ],
  },
  [OCC_CHAT_EMBED_HOST]: {
    welcome: "Ask about Online Compliance Center",
    suggestions: [
      "How do I file a support ticket?",
      "Search the help articles for onboarding",
      "Show my open Zammad tickets",
      "What is our data retention policy?",
    ],
  },
};

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

/** Parent → embed: surface handshake/load failures inside CliThread. */
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
  const copy = EMBED_SHELL_COPY[embedHost];
  if (copy) {
    url.searchParams.set("welcome", copy.welcome);
    // Pipe-separated per embed-ui-params (a JSON array also parses).
    url.searchParams.set("suggestions", copy.suggestions.join("|"));
  }
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
 * Boot: shows `@digithings/web` DigichatBootLoader (the composer-outline cube
 * field) on a transparent surface until `digichat:ready` plus the loader's
 * settle + typewriter sequence finish. The iframe stays transparent /
 * opacity-0 underneath so a white default document never flashes on the dark
 * digithings theme.
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
  // The boot overlay crossfades out once digichat:ready lands AND the typed
  // welcome/examples sequence has played, then unmounts (showBoot), so the
  // copy always finishes before the real hero replaces it.
  const [bootSettled, setBootSettled] = useState(false);
  // Typing finished (the loader's settle callback). Fading at ready alone cut
  // the typed welcome/examples off mid-word (datatap types during the load).
  const [sequenceDone, setSequenceDone] = useState(false);
  // Defer iframe src until after mount so we can read the real parent theme
  // (themeInitScript already flipped data-theme) and avoid a wrong-mode flash.
  // Paint the iframe from the first HTML instead of waiting for the mount
  // effect: a deferred src leaves the page showing its own background (the
  // white flash) until hydration. The default theme is corrected by the mount
  // effect right after, if the page runs another one.
  const [src, setSrc] = useState(() => {
    // During hydration the SSR iframe already exists - and the inline theme
    // script may have rewritten its src (light -> dark). Adopt that value so
    // React's first client render matches the DOM; a mismatch here means
    // React never patches src again, which froze the embed on the old theme.
    if (typeof document !== "undefined") {
      const frames = [
        ...document.querySelectorAll<HTMLIFrameElement>("#dc-digichat-frame"),
      ];
      const liveEl = frames.find((el) => el.closest("[hidden]") === null) ?? frames[0];
      const live = liveEl?.getAttribute("src");
      if (live) return live;
    }
    return parseOrigin(embedOrigin) ? embedSrc(embedOrigin, embedHost, "light") : "";
  });
  const [shellTheme, setShellTheme] = useState<EmbedShellTheme>("light");
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
      // The inline script above already rewrote the theme param when the
      // real theme is dark; only rebuild the src when the live attribute
      // still disagrees (client-only mounts, embed target changes).
      // Rebuilding just for the theme reloads the iframe and flashes.
      const current = iframeRef.current?.getAttribute("src") ?? "";
      if (!current.includes(`theme=${theme}`)) {
        setSrc(embedSrc(embedOrigin, embedHost, theme));
      }
    });

    const onThemeAttr = () => {
      const next = readParentDocumentTheme();
      if (next === themeRef.current) return;
      themeRef.current = next;
      setShellTheme(next);
      // Rebuild the embed URL for the new theme: the theme message alone left
      // the app on the old palette (dark composer on a light page). When the
      // URL is unchanged React skips the attribute write, so this cannot
      // reload an already-correct iframe.
      setSrc(embedSrc(embedOrigin, embedHost, next));
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
      setBootSettled(false);
      setSequenceDone(false);
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

  // Hold the overlay for the crossfade once ready AND the typed copy has
  // played, then unmount it. A late ready keeps the overlay docked rather
  // than revealing an unpainted iframe mid-sequence.
  useEffect(() => {
    if (!embedReady || !sequenceDone) return;
    const t = window.setTimeout(() => setBootSettled(true), 360);
    return () => window.clearTimeout(t);
  }, [embedReady, sequenceDone]);

  if (configError) {
    return (
      <p className="dc-page" style={{ padding: "2rem" }}>
        {configError}
      </p>
    );
  }

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
        // Full-bleed: the chat fills the page area edge-to-edge (the DataTap
        // layout), so the themed background reads as one solid surface.
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

      {src && !shellLoadError ? (
        <iframe
          ref={iframeRef}
          id="dc-digichat-frame"
          title="digichat"
          src={src}
          className="dc-chat-frame"
          style={{
            flex: 1,
            width: "100%",
            border: 0,
            minHeight: 0,
            height: "100%",
            // The in-app boot is the only loader now - the iframe stays
            // visible from mount so nothing masks it. Its theme canvas and
            // colour scheme live in globals.css (.dc-chat-frame, keyed on the
            // root [data-theme]) - component state must never disagree with
            // the page theme (dark page + light chat rectangle).
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

      {src ? (
        <script
          // Pre-paint correction: the URL ships theme=light and the real
          // theme is only knowable from the document (themeInitScript already
          // ran). Rewrite the iframe's src before its document commits so dark
          // readers never see the light frame. Inert after hydration.
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=document.documentElement.getAttribute('data-theme')==='light'?'light':'dark';if(t==='dark'){var f=document.getElementById('dc-digichat-frame');var s=f&&f.getAttribute('src');if(s&&s.indexOf('theme=light')>-1){f.setAttribute('src',s.replace('theme=light','theme=dark'));}}}catch(e){}",
          }}
        />
      ) : null}
    </div>
  );
}
