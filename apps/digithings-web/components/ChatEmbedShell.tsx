"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { DIGICHAT } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";
import { BootLabOverlay } from "@digithings/ui/chat/boot-lab";
import { ChatNoticeContent, chatNoticeRootProps } from "@digithings/ui/chat/notice";
import { Button } from "@digithings/ui/ui";
import { signalDigichatBootStep } from "@digithings/ui/chat/boot-signal";
import { isPaletteId } from "@digithings/ui/theme";
import { readAndClearHandoff } from "@/lib/chatHandoff";
import { readInviteToken, stripInviteTokenFromUrl } from "@/lib/inviteToken";

const READY = "digichat:ready";
const SEED = "digichat:seed";
/** Keep in sync with digichat `THEME_MESSAGE_TYPE` (`embed-theme-messages.ts`). */
export const THEME = "digichat:theme";
/** Keep in sync with digichat `PARENT_ERROR_MESSAGE_TYPE`. */
export const PARENT_ERROR = "digichat:parent-error";

/** Match digichat READY_TIMEOUT_MS — CF Container cold start can exceed 15s. */
export const EMBED_READY_TIMEOUT_MS = 30_000;

/**
 * Warmup cover: the digichat Container scales to zero, so the first visit
 * after an idle period waits 15-25s with no document inside the frame (the
 * Worker blocks the request while the container wakes). Delay the loader past
 * the warm path (~0.6s) so ordinary navigation never flashes an animation,
 * then hold it until `digichat:ready` and crossfade to the real frame.
 */
export const WARMUP_DELAY_MS = 700;

/** Must cover the overlay's opacity transition below. */
export const WARMUP_FADE_MS = 360;

/**
 * Service warm-up (sleep-on-idle backends: auth, assistant, search). digichat
 * serves `/api/embed/warmup` on the embed origin; it reports `ready` only once
 * every service the tenant needs answers. The boot animation shows a
 * "wake up services" step that completes on that edge, and the chat is not
 * revealed before it, so nothing can be sent into a sleeping stack. A cold
 * stack boot takes a few minutes, hence the budget; past it the chat is
 * revealed anyway. Same path for the landing pop-up, /chat, and /chat/occ.
 */
export const WARMUP_PATH = "/api/embed/warmup";
export const SERVICES_BUDGET_MS = 240_000;
const SERVICES_POLL_MS = 3_000;
const SERVICES_PROBE_TIMEOUT_MS = 60_000;
/** Shown on the step before the first probe answers. */
const DEFAULT_SERVICES = ["auth", "assistant"] as const;

export type WarmupProbe = { ready?: boolean; services?: Record<string, string> };

/** Poll warm-up until every service is ready or the budget is spent. */
export async function waitForServices(
  origin: string,
  opts: {
    isCancelled: () => boolean;
    onServices?: (names: string[]) => void;
    budgetMs?: number;
    fetchImpl?: typeof fetch;
    sleep?: (ms: number) => Promise<void>;
    now?: () => number;
  },
): Promise<boolean> {
  const doFetch = opts.fetchImpl ?? fetch;
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const now = opts.now ?? Date.now;
  const t0 = now();
  const budget = opts.budgetMs ?? SERVICES_BUDGET_MS;
  while (!opts.isCancelled() && now() - t0 < budget) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), SERVICES_PROBE_TIMEOUT_MS);
      const res = await doFetch(`${origin.replace(/\/$/, "")}${WARMUP_PATH}`, {
        cache: "no-store",
        credentials: "same-origin",
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      const body = (await res.json()) as WarmupProbe;
      if (body.services) opts.onServices?.(Object.keys(body.services));
      if (body.ready === true) return true;
    } catch {
      /* still waking (or the probe timed out) */
    }
    if (opts.isCancelled()) break;
    await sleep(SERVICES_POLL_MS);
  }
  return false;
}

/**
 * First-paint copy and the host keys it is indexed by now live in
 * `@/lib/embedCopy`, so the landing page's FAQ band can mount the same
 * conversation with the same welcome and the same examples. Re-exported here
 * rather than moved away: this module's importers (the /chat routes, the
 * contract test) keep the surface they already had.
 */
export {
  DEFAULT_CHAT_EMBED_HOST,
  EMBED_SHELL_COPY,
  OCC_CHAT_EMBED_HOST,
} from "@/lib/embedCopy";
import {
  DEFAULT_CHAT_EMBED_HOST,
  EMBED_SHELL_COPY,
} from "@/lib/embedCopy";

export type EmbedShellTheme = "light" | "dark";

export type EmbedParentErrorCode = "ready_timeout" | "embed_unloadable";

/** Read parent digithings.ai `[data-theme]` (ThemeProvider / themeInitScript). */
export function readParentDocumentTheme(
  el: { getAttribute(name: string): string | null } = document.documentElement,
): EmbedShellTheme {
  return el.getAttribute("data-theme") === "light" ? "light" : "dark";
}

/** Parent `[data-palette]`. Absent means the default look. */
export function readParentDocumentPalette(
  el: { getAttribute(name: string): string | null } = document.documentElement,
): string | undefined {
  const value = el.getAttribute("data-palette")?.trim().toLowerCase();
  // Only a known id crosses the frame; anything else is the default look.
  if (!value || !isPaletteId(value)) return undefined;
  return value;
}

export function buildEmbedThemeMessage(
  theme: EmbedShellTheme,
  ts = Date.now(),
  palette?: string,
): { type: typeof THEME; theme: EmbedShellTheme; ts: number; palette?: string } {
  return palette ? { type: THEME, theme, ts, palette } : { type: THEME, theme, ts };
}

/** Parent → embed: surface handshake/load failures inside CliThread. */
export function buildEmbedParentErrorMessage(
  code: EmbedParentErrorCode,
  ts = Date.now(),
): { type: typeof PARENT_ERROR; code: EmbedParentErrorCode; ts: number } {
  return { type: PARENT_ERROR, code, ts };
}

/**
 * What a visitor reads when the chat never loads (the embed answered an error
 * page, never painted, or the build has no embed origin). User-facing only:
 * no env var names, origins or container internals ever reach the page.
 */
// Same words as the embed's own `embed_unloadable` line
// (apps/digichat/src/lib/embed-parent-error-messages.ts); keep the two in step.
export const EMBED_LOAD_ERROR_TITLE = "The chat could not load. Please try again in a moment.";
export const EMBED_LOAD_ERROR_RETRY = "Retry";

/**
 * Operator detail for the same failure. Console only, and only outside
 * production builds: never rendered.
 */
export function formatShellLoadDiagnostic(reason: string): string {
  return (
    `digichat embed failed to load (${reason}) — check DIGICHAT_EMBED_ORIGIN and ` +
    "Container readiness"
  );
}

function logEmbedLoadFailure(reason: string): void {
  if (process.env.NODE_ENV === "production") return;
  console.error(formatShellLoadDiagnostic(reason));
}

/**
 * The class the digichat embed puts on its root (apps/digichat
 * `embed-route-shell.tsx`). A contract test reads that source, so a rename
 * there fails CI instead of turning every /chat load into the error card.
 */
export const EMBED_SHELL_CLASS = "dc-embed-shell";

type FrameLike = { contentDocument: Document | null } | null | undefined;

function readableDocument(frame: FrameLike): Document | null {
  try {
    const doc = frame?.contentDocument;
    if (!doc || doc.URL === "about:blank") return null;
    return doc;
  } catch {
    return null;
  }
}

/**
 * True when the frame loaded a document that is not the chat: an error page
 * (500, 503, a platform error), a 404, or anything else without the embed
 * shell. Only knowable same-origin (production serves /embed on the page's
 * own origin); a cross-origin frame reads as "unknown" and the ready timeout
 * decides instead.
 */
export function embedDocumentFailed(frame: FrameLike): boolean {
  const doc = readableDocument(frame);
  return doc ? doc.querySelector(`.${EMBED_SHELL_CLASS}`) === null : false;
}

/**
 * True only when the frame is readable and really holds the chat. A frame we
 * cannot read (cross-origin) is not assumed to be the chat: on the ready
 * timeout it gets the error card, never a force-reveal of an unknown page.
 */
export function embedDocumentIsChat(frame: FrameLike): boolean {
  const doc = readableDocument(frame);
  return doc ? doc.querySelector(`.${EMBED_SHELL_CLASS}`) !== null : false;
}

/**
 * The in-chat error notice (`@digithings/ui` chat-notice, the box a failed
 * turn shows) centered in the chat slot, with the same Retry action.
 */
export function EmbedLoadErrorCard({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      data-thread-skin="digichat"
      data-slot="embed-load-error"
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.5rem",
        minHeight: 0,
      }}
    >
      <div {...chatNoticeRootProps("error", "max-w-md")}>
        <ChatNoticeContent
          tone="error"
          title={EMBED_LOAD_ERROR_TITLE}
          extra={
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onRetry}
              className="aui-message-error-retry mt-2 shrink-0 items-center self-start border-destructive/25 bg-transparent text-destructive hover:bg-destructive/10"
            >
              {EMBED_LOAD_ERROR_RETRY}
            </Button>
          }
        />
      </div>
    </div>
  );
}

function parseOrigin(raw: string): string {
  try {
    return new URL(raw).origin;
  } catch {
    return "";
  }
}

function embedSrc(
  origin: string,
  embedHost: string,
  theme: EmbedShellTheme,
  inviteToken?: string,
): string {
  const base = origin.replace(/\/$/, "");
  const url = new URL(`${base}/embed`);
  url.searchParams.set("host", embedHost);
  url.searchParams.set("layout", "page");
  url.searchParams.set("theme", theme);
  // Full-page host, not a narrow widget — drop digichat-ui's 1080px reading
  // column so the session fills the shell (see .dc-session--wide).
  url.searchParams.set("wide", "1");
  // Invite key for a gated tenant (DIG-1210). Omitted entirely when absent so a
  // tokenless embed URL is byte-identical to the pre-invite one.
  if (inviteToken) url.searchParams.set("token", inviteToken);
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
  /**
   * Read the invite key off the parent URL and forward it to digichat as
   * `token=` (DIG-1210). Set only on invite-gated routes: /chat leaves it off,
   * so a stray `?token=` there can never reach a tenant that never asked for one.
   *
   * Resolved per visit in the browser, never during render — this app is
   * `output: "export"`, so the shipped HTML is one static artifact shared by
   * every visitor. See `@/lib/inviteToken`.
   */
  acceptsInviteToken?: boolean;
  /**
   * What the cold-start cover paints. `"toolchain"` is the shared
   * BootLabOverlay tool-chain (the landing pop-up's LiveAsk keeps it);
   * `"banner"` is the digichat hero banner alone, for the full-page /chat and
   * /chat/occ routes, where the page is nothing but the chat and a simulated
   * tool list would be inventing work the visitor never started.
   */
  warmupLoader?: "toolchain" | "banner";
};

/**
 * digithings.ai chat shell — iframes digichat /embed (digigraph backend).
 * Requires NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN (digichat Container / Worker origin).
 *
 * Theme: reads parent `html[data-theme]` (shared `dt-theme` / ThemeProvider),
 * pins first paint via `?theme=`, then posts `digichat:theme` on ready and on
 * live toggles so the iframe stays in sync without reload.
 *
 * Boot: digichat's in-app boot chain owns the warm path (it yields on warm
 * nav), but a cold Container has no document to run it in. Until the frame
 * paints, this shell covers the wait with the same `@digithings/ui`
 * BootLabOverlay tool-chain the embed uses — shown only after WARMUP_DELAY_MS so
 * warm loads never flash it, and crossfaded out on `digichat:ready`. Full-page
 * routes (`ChatPageShell`) pass `warmupLoader="banner"` and get the digichat
 * hero banner in the same cover instead. The
 * iframe stays opacity-0 underneath and the frame slot is painted from the
 * first HTML by `.dc-chat-frame` in globals.css (`--chat-frame-canvas` per
 * `[data-theme]`), so a white default document never flashes.
 *
 * Ready failures: posts `digichat:parent-error` into the iframe for in-chat
 * terminal lines when the chat painted but never said ready. When the frame
 * holds an error page, or never loads, the shell centers the in-chat error
 * card (user-facing copy + Retry) in the chat slot instead.
 */
export function ChatEmbedShell({
  embedOrigin,
  embedHost = DEFAULT_CHAT_EMBED_HOST,
  acceptsInviteToken = false,
  warmupLoader = "toolchain",
}: ChatEmbedShellProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeLoadedRef = useRef(false);
  const embedReadyRef = useRef(false);
  const themeRef = useRef<EmbedShellTheme>("dark");
  const paletteRef = useRef<string | undefined>(undefined);
  /** The embed never became the chat (error page, no frame, no ready). */
  const [loadFailed, setLoadFailed] = useState(false);
  /** Bumped by Retry: remounts the frame and restarts the ready wait. */
  const [attempt, setAttempt] = useState(0);
  const [embedReady, setEmbedReady] = useState(false);
  // Every sleep-on-idle service answered warm-up (or the budget was spent).
  const [servicesReady, setServicesReady] = useState(false);
  const [serviceNames, setServiceNames] = useState<string[]>([...DEFAULT_SERVICES]);
  // Ready-timeout / load-error paths reveal the frame regardless of warm-up,
  // so the in-chat error line is visible.
  const [forceReveal, setForceReveal] = useState(false);
  const revealed = (embedReady && servicesReady) || forceReveal;
  // Warmup overlay lifecycle: mounts only when ready is late (cold Container),
  // unmounts after the crossfade once ready lands.
  const [warmupMounted, setWarmupMounted] = useState(false);
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
  const configError = !targetOrigin;
  useEffect(() => {
    if (configError) logEmbedLoadFailure("invalid NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN");
  }, [configError]);

  useEffect(() => {
    if (!targetOrigin) return;
    const theme = readParentDocumentTheme();
    themeRef.current = theme;
    paletteRef.current = readParentDocumentPalette();
    // Defer setState out of the synchronous effect body — react-hooks/set-state-in-effect.
    queueMicrotask(() => {
      setShellTheme(theme);
      // Invite key, read from the live URL (DIG-1210). Resolved here rather
      // than during render: the SSR pass cannot see the query, and the exported
      // HTML must not carry one visitor's key to the next.
      const token = acceptsInviteToken
        ? readInviteToken(window.location.search)
        : undefined;
      // The key has been read and now lives only in this effect's local state
      // for the session, so it has no further reason to sit in the address bar
      // (DIG-1437). Never a store, a cookie or sessionStorage.
      const stripped = token ? stripInviteTokenFromUrl(window.location.href) : null;
      if (stripped) window.history.replaceState(null, "", stripped);
      // The inline script above already rewrote the theme param when the
      // real theme is dark; only rebuild the src when the live attribute
      // still disagrees (client-only mounts, embed target changes).
      // Rebuilding just for the theme reloads the iframe and flashes.
      const current = iframeRef.current?.getAttribute("src") ?? "";
      // The exported first paint never had the key, so an invite link needs one
      // extra src swap on hydration even when the theme already agrees. Any
      // other visitor's src is left alone: no token means no rebuild.
      const missingToken = Boolean(token) && !current.includes("token=");
      if (!current.includes(`theme=${theme}`) || missingToken) {
        setSrc(embedSrc(embedOrigin, embedHost, theme, token));
      }
    });

    const onThemeAttr = () => {
      const next = readParentDocumentTheme();
      const palette = readParentDocumentPalette();
      if (next === themeRef.current && palette === paletteRef.current) return;
      themeRef.current = next;
      paletteRef.current = palette;
      setShellTheme(next);
      // Live toggles post digichat:theme. Rebuilding `src` reloads the iframe
      // and drops the session. The ready handler posts themeRef if the frame
      // has not said ready yet, so a toggle during boot still lands.
      if (!embedReadyRef.current) return;
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      win.postMessage(buildEmbedThemeMessage(next, Date.now(), palette), targetOrigin);
    };
    const observer = new MutationObserver(onThemeAttr);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "data-palette"],
    });
    return () => observer.disconnect();
  }, [acceptsInviteToken, embedOrigin, embedHost, targetOrigin]);

  useEffect(() => {
    if (!targetOrigin) return;

    let ready = false;
    iframeLoadedRef.current = false;
    embedReadyRef.current = false;
    // Defer setState out of the synchronous effect body — react-hooks/set-state-in-effect.
    queueMicrotask(() => {
      setLoadFailed(false);
      setEmbedReady(false);
    });

    function onMessage(ev: MessageEvent) {
      if (ev.origin !== targetOrigin) return;
      const data = ev.data as { type?: string } | null;
      if (!data || data.type !== READY) return;
      ready = true;
      embedReadyRef.current = true;
      setEmbedReady(true);
      setLoadFailed(false);
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      // Always sync theme on ready (covers cold load + late handshake).
      win.postMessage(
        buildEmbedThemeMessage(themeRef.current, Date.now(), readParentDocumentPalette()),
        targetOrigin,
      );
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
      if (iframeLoadedRef.current && win && embedDocumentIsChat(iframeRef.current)) {
        // The chat painted but never said ready — surface inside its transcript.
        win.postMessage(buildEmbedParentErrorMessage("ready_timeout"), targetOrigin);
        // Reveal the iframe so the in-chat error line is visible.
        setEmbedReady(true);
        setForceReveal(true);
        return;
      }
      // Never loaded, or loaded something we cannot confirm is the chat (an
      // error page, or a cross-origin frame): the error card in the chat slot.
      logEmbedLoadFailure(
        iframeLoadedRef.current
          ? "no digichat:ready and the frame is not a readable chat"
          : "no digichat:ready and the frame never loaded",
      );
      setLoadFailed(true);
    }, EMBED_READY_TIMEOUT_MS);
    return () => {
      window.removeEventListener("message", onMessage);
      window.clearTimeout(t);
    };
  }, [targetOrigin, attempt]);

  // Wake every service before the chat is revealed (boot step "services").
  // Same-origin only: the probe is a plain GET on the embed origin, and a
  // cross-origin embed (local dev) skips the step rather than wait on CORS.
  useEffect(() => {
    if (!targetOrigin) return;
    let cancelled = false;
    const sameOrigin = targetOrigin === window.location.origin;
    void (async () => {
      if (sameOrigin) {
        await waitForServices(targetOrigin, {
          isCancelled: () => cancelled,
          onServices: (names) => {
            if (!cancelled && names.length) setServiceNames(names);
          },
        });
      }
      if (cancelled) return;
      signalDigichatBootStep("services");
      setServicesReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [targetOrigin]);

  // Cold-start cover: only after a warm load has had its chance
  // (WARMUP_DELAY_MS), so ordinary navigation never flashes a loader. setState
  // lives in the timer callback (react-hooks/set-state-in-effect).
  useEffect(() => {
    if (revealed || loadFailed) return;
    const t = window.setTimeout(() => setWarmupMounted(true), WARMUP_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [revealed, loadFailed]);

  // Unmount after the crossfade has run (the overlay is opacity-0 by then).
  useEffect(() => {
    if (!warmupMounted || !revealed) return;
    const t = window.setTimeout(() => setWarmupMounted(false), WARMUP_FADE_MS);
    return () => window.clearTimeout(t);
  }, [warmupMounted, revealed]);

  // Retry reloads the embed in place: the invite key (if any) already lives in
  // `src`, and a page reload would lose it once the address bar was stripped.
  // The ready effect (keyed on `attempt`) resets the load refs.
  const retryEmbed = () => {
    setLoadFailed(false);
    setForceReveal(false);
    setEmbedReady(false);
    setAttempt((n) => n + 1);
  };

  if (configError) {
    // A build with no embed origin cannot recover in place; reload the page.
    return (
      <div
        data-theme={shellTheme}
        style={{
          display: "flex",
          flexDirection: "column",
          flex: 1,
          height: "100%",
          minHeight: "100%",
          width: "100%",
          colorScheme: shellTheme,
        }}
      >
        <EmbedLoadErrorCard onRetry={() => window.location.reload()} />
      </div>
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
        // Transparent, not a second var(--bg) fill: the page ground is already
        // that color, and an opaque rectangle here flashes when the embed loads.
        // The white-flash guard lives on the frame itself (`.dc-chat-frame`
        // paints --chat-frame-canvas pre-paint) and inside the iframe's own boot.
        background: "transparent",
        colorScheme: shellTheme,
      }}
    >
      {loadFailed ? <EmbedLoadErrorCard onRetry={retryEmbed} /> : null}

      {warmupMounted && !loadFailed ? (
        <div
          aria-busy={!revealed}
          aria-live="polite"
          aria-hidden={revealed}
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 1,
            // Crossfade to the real frame on ready; transparent so the page
            // ground keeps showing through (same reasoning as the shell above).
            opacity: revealed ? 0 : 1,
            transition: "opacity 320ms ease",
            pointerEvents: revealed ? "none" : "auto",
            background: "transparent",
          }}
        >
          {warmupLoader === "banner" ? (
            // Full-page chat (/chat, /chat/occ): the digichat hero banner
            // alone, centered both ways. No copy and no spinner — the page is
            // the chat, so the cover is the product's own mark playing its
            // LOADING pass. The wrapper is what gives the canvas a width;
            // HeroBanner sizes itself to its container.
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: "100%",
                height: "100%",
              }}
            >
              <div style={{ width: "min(560px, 72vw)" }}>
                <HeroBanner def={DIGICHAT} replayLoading />
              </div>
              <span className="sr-only">Loading chat…</span>
            </div>
          ) : (
            <BootLabOverlay
              // The canonical tool-chain boot: rows pull the image, mount the
              // configuration, warm the runtime, then the last row waits for the
              // app's real ready edge — the digichat:ready postMessage, passed
              // through as readyEdge because the app runs in another document.
              // Facts are the deployment's real values (never invented counts):
              // both live tenants run the digigraph backend.
              variant="tooltask"
              // The last rows wait on real edges: "wake up services" on the
              // warm-up probe, "wire in the backend" on digichat:ready.
              ready={revealed}
              readyEdge={revealed}
              onSettled={() => {}}
              facts={{
                starters: EMBED_SHELL_COPY[embedHost]?.suggestions.length,
                backend: "digigraph",
                services: serviceNames,
              }}
            />
          )}
        </div>
      ) : null}

      {src && !loadFailed ? (
        <iframe
          key={attempt}
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
            // Hidden until ready so the browser-default white document never
            // paints through the warmup overlay (or, with no overlay on a warm
            // load, before the app's own theme canvas is up). Its theme canvas
            // and colour scheme live in globals.css (.dc-chat-frame, keyed on
            // the root [data-theme]) - component state must never disagree
            // with the page theme (dark page + light chat rectangle).
            opacity: revealed ? 1 : 0,
            transition: "opacity 320ms ease",
            position: "relative",
            zIndex: 0,
          }}
          allow="clipboard-write"
          onLoad={() => {
            iframeLoadedRef.current = true;
            // Same-origin error page (the container's 500, a 503 while the
            // slot is busy): show the card now rather than after the ready
            // timeout, and never reveal the raw error document.
            if (embedDocumentFailed(iframeRef.current)) {
              logEmbedLoadFailure("the frame loaded an error page");
              setLoadFailed(true);
              return;
            }
            setLoadFailed(false);
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
