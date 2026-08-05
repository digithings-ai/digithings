"use client";

import { useEffect, useRef, useState } from "react";
import { readAndClearHandoff } from "@/lib/chatHandoff";
import { buildDigichatEmbedSrc, getDigichatEmbedOrigin } from "@/lib/digichatEmbed";
import {
  CHAT_LOAD_ERROR_COPY,
  createSeedPayload,
  READY_TIMEOUT_MS,
  shouldAcceptReady,
} from "@/lib/digichatSeedBridge";

export function ChatEmbedShell() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const handoffRef = useRef(readAndClearHandoff());
  const readySeen = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const digichatOrigin = getDigichatEmbedOrigin();
  const src = buildDigichatEmbedSrc({ parentOrigin: "https://digithings.ai" });

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (!shouldAcceptReady(event, digichatOrigin)) return;
      readySeen.current = true;
      setError(null);
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      const handoff = handoffRef.current;
      handoffRef.current = null;
      if (handoff) {
        win.postMessage(createSeedPayload(handoff), digichatOrigin);
      }
    };
    window.addEventListener("message", onMessage);
    const t = window.setTimeout(() => {
      if (!readySeen.current) setError(CHAT_LOAD_ERROR_COPY);
    }, READY_TIMEOUT_MS);
    return () => {
      window.removeEventListener("message", onMessage);
      window.clearTimeout(t);
    };
  }, [digichatOrigin]);

  return (
    <main
      className="dc-page"
      style={{ display: "flex", flexDirection: "column", minHeight: "calc(100vh - 4rem)" }}
    >
      {error ? (
        <p role="alert" style={{ padding: "1.5rem" }}>
          {error}{" "}
          <button type="button" onClick={() => window.location.reload()}>
            Refresh
          </button>
        </p>
      ) : null}
      <iframe
        ref={iframeRef}
        title="digichat"
        src={src}
        style={{ flex: 1, width: "100%", border: 0, minHeight: "70vh" }}
        onError={() => setError(CHAT_LOAD_ERROR_COPY)}
      />
    </main>
  );
}
