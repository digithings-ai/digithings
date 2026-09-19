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

/**
 * Same-window signal that the boot overlay has left the stage (it starts
 * fading). Surfaces that hold their choreography until the handoff - e.g. the
 * welcome typewriter in "takeover" handoff mode - listen for it.
 */
export const DIGI_CHAT_REVEALED_EVENT = "digichat:boot-revealed";

/** Mark the boot handoff as started for this document (idempotent). */
export function signalDigichatRevealed(): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.digichatRevealed = "1";
  window.dispatchEvent(new Event(DIGI_CHAT_REVEALED_EVENT));
}

/** Whether the boot handoff already started in this document. */
export function hasDigichatRevealed(): boolean {
  return (
    typeof document !== "undefined" &&
    document.documentElement.dataset.digichatRevealed === "1"
  );
}

/**
 * Boot-step channel: the app reports real milestones as they happen
 * (deployment configuration applied, chat runtime up) so the boot animation
 * can complete its rows against the actual boot instead of a fixed timeline.
 */
export const DIGI_CHAT_BOOT_STEP_EVENT = "digichat:boot-step";

/** Real boot milestones the app reports. */
export type DigichatBootStep = "config" | "runtime";

/** Report a real boot milestone for this document (idempotent per step). */
export function signalDigichatBootStep(step: DigichatBootStep): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const done = root.dataset.digichatBootSteps?.split(",") ?? [];
  if (done.includes(step)) return;
  root.dataset.digichatBootSteps = [...done, step].join(",");
  window.dispatchEvent(
    new CustomEvent(DIGI_CHAT_BOOT_STEP_EVENT, { detail: step }),
  );
}

/** Boot milestones already reported in this document. */
export function digichatBootSteps(): readonly string[] {
  if (typeof document === "undefined") return [];
  return document.documentElement.dataset.digichatBootSteps?.split(",") ?? [];
}

/** Milliseconds since this document started loading (boot clock). */
export function digichatBootClockMs(): number {
  return typeof performance === "undefined" ? 0 : performance.now();
}

/**
 * Lab switch: `?handoff=` picks how the boot hands off to the chat.
 * Comma-separated: `reveal` (re-run the hero entrance), `type` (welcome
 * takeover), `drift` (motion match), `beat` (pause before the fade).
 */
export type DigichatHandoff = {
  reveal: boolean;
  type: boolean;
  drift: boolean;
  beat: boolean;
};

/**
 * Parse the `?handoff=` lab switch. The reveal hand-off ships by default;
 * `?handoff=none` (or `off`) restores the hard cut, and any other comma list
 * opts into exactly those modes.
 */
export function resolveHandoff(): DigichatHandoff {
  const off: DigichatHandoff = {
    reveal: false,
    type: false,
    drift: false,
    beat: false,
  };
  if (typeof window === "undefined") return off;
  const raw = new URLSearchParams(window.location.search).get("handoff");
  if (raw === null) return { ...off, reveal: true };
  const modes = new Set(
    raw
      .split(",")
      .map((mode) => mode.trim())
      .filter(Boolean),
  );
  if (modes.has("none") || modes.has("off")) return off;
  return {
    reveal: modes.has("reveal"),
    type: modes.has("type"),
    drift: modes.has("drift"),
    beat: modes.has("beat"),
  };
}
