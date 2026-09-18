/**
 * Same-window signal that the DigiChat boot animation has settled.
 * DigichatBootLoader dispatches it; surfaces that reveal copy after the boot
 * (e.g. the welcome body typewriter) listen for it so their animation is not
 * spent behind a boot overlay.
 */
export const DIGI_CHAT_READY_EVENT = "digichat:ready";

/** Mark the boot as settled for this document (idempotent). */
export function signalDigichatReady(): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.digichatReady = "1";
  window.dispatchEvent(new Event(DIGI_CHAT_READY_EVENT));
}

/** Whether the boot already settled in this document. */
export function hasDigichatReady(): boolean {
  return (
    typeof document !== "undefined" &&
    document.documentElement.dataset.digichatReady === "1"
  );
}
