/**
 * Welcome slot for the landing-page digichat simulation (#4429, Stage 8).
 *
 * Ported from the design reference's `digichat-thread-welcome.tsx`. Mounted as
 * the Thread's official `components.Welcome` override, which the gallery Thread
 * renders in `ViewportFooter` — immediately above the composer, bottom-aligned —
 * so the copy reads as an introduction to the box rather than as an empty state
 * pinned to the top of a blank transcript.
 *
 * The title is an `h3`, not the `h1` the reference uses. On the reference's
 * specimen page the thread *is* the page, so its greeting is the page title; on
 * the landing page the thread is a widget inside the FAQ band, and an `h1` there
 * gave the marketing page two top-level headings — the hero's and a chat
 * greeting. `h3` nests it under that band's own `h2`, which is where it belongs.
 * The kit's default (`gallery-thread/thread.aui.tsx`) keeps its `h1`: on `/chat`
 * and in the embed the thread really is the document.
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
      <h3 className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in fill-mode-both text-2xl tracking-tight duration-200">
        {title}
      </h3>
      {body.map((line, index) => (
        <p key={`${index}:${line}`} className="aui-thread-welcome-copy">
          {line}
        </p>
      ))}
    </div>
  );
}
