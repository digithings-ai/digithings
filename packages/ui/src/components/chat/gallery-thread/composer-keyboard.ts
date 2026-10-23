/**
 * Composer keyboard dismissal for phones.
 *
 * On a phone the software keyboard covers most of the viewport, so sending a
 * message leaves the visitor looking at the first lines of the answer with the
 * keyboard still up. Dropping focus from the textarea retracts the keyboard and
 * gives the streaming answer the whole screen.
 *
 * Scoped to a coarse pointer on purpose: on a desktop the caret belongs in the
 * composer for the follow-up turn, and losing focus there would be a
 * regression.
 */

type MatchMedia = ((query: string) => MediaQueryList) | undefined;

function defaultMatchMedia(): MatchMedia {
  return typeof window === "undefined" ? undefined : window.matchMedia;
}

/** True on a phone or tablet, where the pointer is a finger. */
export function isCoarsePointer(matchMedia: MatchMedia = defaultMatchMedia()): boolean {
  if (typeof matchMedia !== "function") return false;
  try {
    return matchMedia("(pointer: coarse)").matches;
  } catch {
    return false;
  }
}

/**
 * True when the composer holds something the user meant to send.
 *
 * Read *before* the submit is handed to the runtime: a successful send clears
 * the textarea, so asking afterwards would answer "empty" for every real send.
 * Enter on an empty composer also submits through the same form, and that one
 * must not steal focus.
 */
export function composerHasText(root: HTMLElement | null): boolean {
  if (!root) return false;
  const area = root.querySelector<HTMLTextAreaElement>("textarea");
  return area ? area.value.trim().length > 0 : false;
}

/**
 * Blur the composer's textarea so the on-screen keyboard retracts.
 *
 * Returns true when the textarea had focus and was blurred, so a caller (or a
 * test) can tell a dismissal from a no-op. Never throws: a missing textarea on
 * a skin that does not use one is a valid state.
 */
export function dismissComposerKeyboard(
  root: HTMLElement | null,
  options: { coarse?: boolean } = {},
): boolean {
  const coarse = options.coarse ?? isCoarsePointer();
  if (!coarse || !root) return false;
  const area = root.querySelector<HTMLTextAreaElement>("textarea");
  if (!area) return false;
  const wasFocused = area.ownerDocument.activeElement === area;
  area.blur();
  return wasFocused;
}
