"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { readAndClearHandoff } from "@/lib/chatHandoff";

const READY = "digichat:ready";
const SEED = "digichat:seed";

function embedSrc(origin: string): string {
  const base = origin.replace(/\/$/, "");
  const url = new URL(`${base}/embed`);
  url.searchParams.set("host", "digithings.ai");
  url.searchParams.set("layout", "page");
  return url.toString();
}

/**
 * digithings.ai/chat shell — iframes digichat /embed (digigraph backend).
 * Requires NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN (tunnel hostname to digichat Node).
 */
export function ChatEmbedShell({ embedOrigin }: { embedOrigin: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [error, setError] = useState<string | null>(null);
  const src = useMemo(() => embedSrc(embedOrigin), [embedOrigin]);
  const targetOrigin = useMemo(() => {
    try {
      return new URL(embedOrigin).origin;
    } catch {
      return "";
    }
  }, [embedOrigin]);

  useEffect(() => {
    if (!targetOrigin) {
      setError("Invalid NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN");
      return;
    }

    function onMessage(ev: MessageEvent) {
      if (ev.origin !== targetOrigin) return;
      const data = ev.data as { type?: string } | null;
      if (!data || data.type !== READY) return;
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

    let ready = false;
    function onMessageReady(ev: MessageEvent) {
      onMessage(ev);
      const data = ev.data as { type?: string } | null;
      if (ev.origin === targetOrigin && data?.type === READY) {
        ready = true;
        setError(null);
      }
    }
    window.addEventListener("message", onMessageReady);
    const t = window.setTimeout(() => {
      if (!ready) {
        setError("digichat embed did not signal ready — check tunnel and DIGICHAT_EMBED_HOSTS");
      }
    }, 15_000);
    return () => {
      window.removeEventListener("message", onMessageReady);
      window.clearTimeout(t);
    };
  }, [targetOrigin]);

  if (error && !targetOrigin) {
    return (
      <p className="dc-page" style={{ padding: "2rem" }}>
        {error}
      </p>
    );
  }

  return (
    <div className="dc-page" style={{ display: "flex", flexDirection: "column", minHeight: "calc(100vh - 4rem)" }}>
      {error ? (
        <p style={{ padding: "0.75rem 1rem", opacity: 0.8 }} role="status">
          {error}
        </p>
      ) : null}
      <iframe
        ref={iframeRef}
        title="digichat"
        src={src}
        style={{ flex: 1, width: "100%", border: 0, minHeight: "70vh" }}
        allow="clipboard-write"
        onLoad={() => setError(null)}
      />
    </div>
  );
}
