/**
 * Welcome slot for the gallery Thread.
 * Official override: Thread `components.Welcome`
 * (https://www.assistant-ui.com/elements/thread).
 * Mounted in ViewportFooter immediately above the composer — not at the top.
 * Copy comes from deploy-shaped config — not a generic “ask anything” line.
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
      className="aui-thread-welcome-root flex flex-col items-start text-left"
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
