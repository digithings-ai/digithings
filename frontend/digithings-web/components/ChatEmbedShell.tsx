"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { readAndClearHandoff } from "@/lib/chatHandoff";

const READY = "digichat:ready";
const SEED = "digichat:seed";

function parseOrigin(raw: string): string {
  try {
    return new URL(raw).origin;
  } catch {
    return "";
  }
}

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
  const [readyError, setReadyError] = useState<string | null>(null);
  const targetOrigin = useMemo(() => parseOrigin(embedOrigin), [embedOrigin]);
  const configError = targetOrigin
    ? null
    : "Invalid NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN";
  const src = useMemo(
    () => (targetOrigin ? embedSrc(embedOrigin) : ""),
    [embedOrigin, targetOrigin],
  );

  useEffect(() => {
    if (!targetOrigin) return;

    let ready = false;
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
      if (!ready) {
        setReadyError(
          "digichat embed did not signal ready — check tunnel and DIGICHAT_EMBED_HOSTS",
        );
      }
    }, 15_000);
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
        minHeight: "calc(100vh - 4rem)",
      }}
    >
      {readyError ? (
        <p style={{ padding: "0.75rem 1rem", opacity: 0.8 }} role="status">
          {readyError}
        </p>
      ) : null}
      <iframe
        ref={iframeRef}
        title="digichat"
        src={src}
        style={{ flex: 1, width: "100%", border: 0, minHeight: "70vh" }}
        allow="clipboard-write"
        onLoad={() => setReadyError(null)}
      />
    </div>
  );
}
