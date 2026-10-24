"use client";

/**
 * Designed wait / empty / failure states for the digichat app shell.
 *
 * Audit T4: the shell used to drop its states — a bare "Loading…" line, an
 * unstyled sidebar sentence, and a muted "Could not load…" with a link. Each
 * state now says what is happening in the house voice: terminal lines on the
 * mono grid, a hairline rule, ink that clears AA, and an action that names
 * what it does. No spinner (canon: motion is the block caret), and reduced
 * motion gets the label whole rather than a blank surface.
 *
 * Frames: `.app-shell-wait`, `.app-state*` in `src/styles/app-shell-states.css`.
 */

import { ContainerBootLoader } from "@digithings/ui";

/** Real phases of this wait — the shell reads local threads, then the server. */
export const CHAT_SHELL_BOOT_STEPS = [
  "restoring your session",
  "loading your conversations",
  "opening the thread",
];

export function ChatShellLoading({
  steps = CHAT_SHELL_BOOT_STEPS,
}: {
  steps?: string[];
}) {
  return (
    <div className="app-shell-wait" aria-busy="true" aria-label="Loading digichat">
      <ContainerBootLoader title="digichat" steps={steps} />
    </div>
  );
}

/** Sidebar state when there is no thread to list (or none matches). */
export function ChatShellEmpty({ query }: { query: string }) {
  return (
    <p className="app-sidebar-state" role="status">
      <span className="app-sidebar-state-mark" aria-hidden="true">
        ·
      </span>
      {query.trim() ? "No chats match that search." : "No chats yet."}
    </p>
  );
}

/** The active thread failed to hydrate; the row stays on the server. */
export function ChatShellUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="app-state" role="alert">
      <p className="app-state-line">
        <span className="app-state-mark" aria-hidden="true">
          !
        </span>
        Could not load this conversation.
      </p>
      <p className="app-state-note">The thread is still on the server.</p>
      <button type="button" className="app-state-action" onClick={onRetry}>
        retry
      </button>
    </div>
  );
}
