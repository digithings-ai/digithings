"use client";
import { useEffect, useId, useState } from "react";

/**
 * MermaidBlock — renders a ```mermaid fenced block from streamed model output as
 * an SVG diagram, so the assistant can visualize pipelines and architecture.
 *
 * Safety: mermaid is initialized with `securityLevel: "strict"` (HTML labels off,
 * click handlers/scripts stripped) and the source is attacker-influenceable model
 * text. We render via `mermaid.render()`, which returns an SVG *string* that we
 * inject into a contained node — the only `innerHTML` use on the site, justified
 * by strict mode + the fact that mermaid sanitizes its own output. The library is
 * lazy-imported (dynamic `import`) so it stays out of the initial bundle (the site
 * is a static export and most visitors never see a diagram).
 *
 * The raw source stays one click away via a "view source" toggle, and any parse
 * error falls back to showing the code verbatim — never a broken diagram.
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

  // Parse error (or unsupported syntax): show the source so nothing is lost.
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
      {svg && (
        <button
          type="button"
          className="dc-mermaid-toggle"
          aria-expanded={showSource}
          onClick={() => setShowSource((v) => !v)}
        >
          {showSource ? "▾ hide source" : "▸ view source"}
        </button>
      )}
      {showSource && (
        <pre className="dc-code-block">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}
