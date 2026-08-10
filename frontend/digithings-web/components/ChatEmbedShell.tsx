"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { readAndClearHandoff } from "@/lib/chatHandoff";

const READY = "digichat:ready";
const SEED = "digichat:seed";

/** Match digichat READY_TIMEOUT_MS — CF Container cold start can exceed 15s. */
export const EMBED_READY_TIMEOUT_MS = 30_000;

/** Default embed host for digithings.ai/chat (client #0). */
export const DEFAULT_CHAT_EMBED_HOST = "digithings.ai";

/** Virtual first-party host for digithings.ai/chat/occ (client #1). */
export const OCC_CHAT_EMBED_HOST = "occ.digithings.ai";

function parseOrigin(raw: string): string {
  try {
    return new URL(raw).origin;
  } catch {
    return "";
  }
}

function embedSrc(origin: string, embedHost: string): string {
  const base = origin.replace(/\/$/, "");
  const url = new URL(`${base}/embed`);
  url.searchParams.set("host", embedHost);
  url.searchParams.set("layout", "page");
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
 */
export function ChatEmbedShell({
  embedOrigin,
  embedHost = DEFAULT_CHAT_EMBED_HOST,
}: ChatEmbedShellProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeLoadedRef = useRef(false);
  const [readyError, setReadyError] = useState<string | null>(null);
  const targetOrigin = useMemo(() => parseOrigin(embedOrigin), [embedOrigin]);
  const configError = targetOrigin
    ? null
    : "Invalid NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN";
  const src = useMemo(
    () => (targetOrigin ? embedSrc(embedOrigin, embedHost) : ""),
    [embedOrigin, targetOrigin, embedHost],
  );

  useEffect(() => {
    if (!targetOrigin) return;

    let ready = false;
    iframeLoadedRef.current = false;
    function onMessage(ev: MessageEvent) {
      if (ev.origin !== targetOrigin) return;
      const data = ev.data as { type?: string } | null;
      if (!data || data.type !== READY) return;
      ready = true;
      setReadyError(null);
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
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
      // Chat can work without the ready handshake (composer still loads). Only
      // surface a banner when the iframe itself never finished loading — a
      // missing ready after a successful load is usually a cold-start race that
      // self-heals, and a permanent banner would steal height from the chat.
      if (!ready && !iframeLoadedRef.current) {
        setReadyError(
          "digichat embed did not load — refresh the page, or try again in a moment if the service is cold-starting.",
        );
      }
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
      {readyError ? (
        <p
          style={{
            flexShrink: 0,
            padding: "0.75rem 1rem",
            opacity: 0.8,
          }}
          role="status"
        >
          {readyError}
        </p>
      ) : null}
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
          setReadyError(null);
        }}
      />
    </div>
  );
}
