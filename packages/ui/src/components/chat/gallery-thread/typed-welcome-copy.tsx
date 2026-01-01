"use client";

/**
 * The welcomeBody lines under the headline. Rendered statically: the picked
 * handoff has no typing, so the copy appears with the hero and nothing
 * reflows (no caret, no ghost spans, no per-character reveal).
 */
export function TypedWelcomeCopy({ lines }: { lines: readonly string[] }) {
  return (
    <>
      {lines.map((line, index) => (
        <p key={`${index}:${line}`} className="aui-thread-welcome-copy">
          {line}
        </p>
      ))}
    </>
  );
}
