/**
 * Welcome slot for the landing-page digichat simulation (#4429, Stage 8).
 *
 * Ported from the design reference's `digichat-thread-welcome.tsx`. Mounted as
 * the Thread's official `components.Welcome` override, which the gallery Thread
 * renders in `ViewportFooter` — immediately above the composer, bottom-aligned —
 * so the copy reads as an introduction to the box rather than as an empty state
 * pinned to the top of a blank transcript.
 */
export function DigichatThreadWelcome({
  title,
  body,
}: {
  title: string;
  body: readonly string[];
}) {
  return (
    <div
      data-slot="aui_thread-welcome"
      className="aui-thread-welcome-root flex flex-col items-start text-start"
    >
      <h1 className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in fill-mode-both text-2xl tracking-tight duration-200">
        {title}
      </h1>
      {body.map((line, index) => (
        <p key={`${index}:${line}`} className="aui-thread-welcome-copy">
          {line}
        </p>
      ))}
    </div>
  );
}
