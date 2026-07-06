"use client";

import { useEffect, useId, useState } from "react";

/**
 * Renders a ```mermaid fenced block as an SVG diagram. Lazy-imports mermaid so
 * it stays out of the initial bundle when no diagram is shown.
 */
export function MermaidBlock({ code }: { code: string }) {
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const id = useId().replace(/:/g, "");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "neutral",
          fontFamily: "var(--font-mono), ui-monospace, monospace",
        });
        const { svg } = await mermaid.render(`dc-mmd-${id}`, code);
        if (!cancelled) setSvg(svg);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, id]);

  if (failed) {
    return (
      <div className="dc-code-block">
        <pre>
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  return (
    <div className="dc-mermaid">
      {svg ? (
        <figure className="dc-mermaid-fig" dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <pre className="dc-code-block">
          <code>{code}</code>
        </pre>
      )}
      {svg ? (
        <button
          type="button"
          className="dc-mermaid-toggle"
          aria-expanded={showSource}
          onClick={() => setShowSource((v) => !v)}
        >
          {showSource ? "▾ hide source" : "▸ view source"}
        </button>
      ) : null}
      {showSource ? (
        <pre className="dc-code-block">
          <code>{code}</code>
        </pre>
      ) : null}
    </div>
  );
}
