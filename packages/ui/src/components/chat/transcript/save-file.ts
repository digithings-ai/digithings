/**
 * Save a generated text file (Markdown or HTML export) from the chat.
 *
 * Phones broke the plain `<a download>` path in two ways:
 *
 * 1. iOS Safari asks "Download …?" before it reads a blob URL. The old code
 *    revoked the URL two seconds after the click, so a visitor who took
 *    longer to confirm got an empty or failed download. The URL now lives
 *    for a minute.
 * 2. A download or share started after the tap's user activation expired
 *    is dropped, silently, inside a cross-origin iframe (the OCC and
 *    digithings.ai embeds). The HTML export runs after the menu closes and
 *    after it inlines fonts and images, which on a phone network outlasts
 *    the activation. When activation is gone we show a "Save" button, so
 *    the save runs inside a fresh tap.
 *
 * On a touch device that can share files (and where the frame is allowed
 * to), the system share sheet is used: it offers "Save to Files" on iOS
 * and is the reliable path there. Desktop keeps the direct download.
 */

/** How long a blob URL outlives its click. iOS reads it after the user confirms. */
export const SAVE_URL_LIFETIME_MS = 60_000;

export const SAVE_PROMPT_SLOT = "export-save-prompt";

type ShareNavigator = Navigator & {
  canShare?: (data: ShareData) => boolean;
  share?: (data: ShareData) => Promise<void>;
  userActivation?: { isActive: boolean };
};

type FeaturePolicyDocument = Document & {
  featurePolicy?: { allowsFeature: (feature: string) => boolean };
  permissionsPolicy?: { allowsFeature: (feature: string) => boolean };
};

type Env = { navigator?: Navigator; matchMedia?: (q: string) => { matches: boolean } };

function coarsePointer(win: Env): boolean {
  try {
    return win.matchMedia?.("(pointer: coarse)").matches === true;
  } catch {
    return false;
  }
}

function shareAllowedInFrame(doc: Document): boolean {
  const policy =
    (doc as FeaturePolicyDocument).permissionsPolicy ??
    (doc as FeaturePolicyDocument).featurePolicy;
  if (!policy) return true;
  try {
    return policy.allowsFeature("web-share");
  } catch {
    return true;
  }
}

/** False only when the browser says the tap's activation is gone. */
export function hasUserActivation(nav: Navigator | undefined): boolean {
  const ua = (nav as ShareNavigator | undefined)?.userActivation;
  return ua ? ua.isActive : true;
}

function canShareFile(win: Env, doc: Document, file: File): boolean {
  const nav = win.navigator as ShareNavigator | undefined;
  if (!nav || typeof File === "undefined") return false;
  if (typeof nav.share !== "function" || typeof nav.canShare !== "function") return false;
  if (!coarsePointer(win) || !shareAllowedInFrame(doc)) return false;
  try {
    return nav.canShare({ files: [file] });
  } catch {
    return false;
  }
}

/** Anchor download. Needs to run inside a user activation in an iframe. */
export function anchorDownload(doc: Document, filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = doc.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  (doc.body ?? doc.documentElement).appendChild(a);
  a.click();
  a.remove();
  const later =
    globalThis.setTimeout ??
    ((fn: () => void) => {
      fn();
      return 0;
    });
  later(() => URL.revokeObjectURL(url), SAVE_URL_LIFETIME_MS);
}

/** Share sheet on a phone, else a download. Call from inside a tap. */
function saveNow(win: Env, doc: Document, filename: string, text: string, mime: string): void {
  const blob = new Blob([text], { type: mime });
  const file = typeof File === "undefined" ? null : new File([text], filename, { type: mime });
  if (file && canShareFile(win, doc, file)) {
    const nav = win.navigator as ShareNavigator;
    nav.share!({ files: [file], title: filename }).catch((error: unknown) => {
      // The visitor closed the sheet: nothing to do.
      if (error instanceof Error && error.name === "AbortError") return;
      anchorDownload(doc, filename, file);
    });
    return;
  }
  anchorDownload(doc, filename, file ?? blob);
}

function removePrompt(doc: Document): void {
  doc.querySelector(`[data-slot='${SAVE_PROMPT_SLOT}']`)?.remove();
}

/**
 * A one-tap "Save" button for an export that finished after the tap's
 * activation expired. Replaces any earlier prompt.
 */
export function showSavePrompt(
  doc: Document,
  filename: string,
  onSave: () => void,
): HTMLElement | null {
  const host = doc.body ?? doc.documentElement;
  if (!host) return null;
  removePrompt(doc);
  const box = doc.createElement("div");
  box.setAttribute("role", "status");
  box.setAttribute("data-slot", SAVE_PROMPT_SLOT);
  box.style.cssText =
    "position:fixed;left:50%;bottom:max(16px,env(safe-area-inset-bottom));transform:translateX(-50%);z-index:2147483000;display:flex;gap:8px;align-items:center;max-width:calc(100vw - 32px);padding:8px 10px;border:1px solid currentColor;background:Canvas;color:CanvasText;font:inherit;font-size:13px;";
  const label = doc.createElement("span");
  label.textContent = `${filename} is ready`;
  label.style.cssText = "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;";
  const save = doc.createElement("button");
  save.type = "button";
  save.textContent = "Save";
  save.setAttribute("data-slot", `${SAVE_PROMPT_SLOT}-save`);
  save.style.cssText =
    "font:inherit;padding:4px 10px;border:1px solid currentColor;background:transparent;color:inherit;cursor:pointer;";
  save.addEventListener("click", () => {
    removePrompt(doc);
    onSave();
  });
  const close = doc.createElement("button");
  close.type = "button";
  close.textContent = "×";
  close.setAttribute("aria-label", "Dismiss");
  close.style.cssText =
    "font:inherit;padding:2px 6px;border:0;background:transparent;color:inherit;cursor:pointer;";
  close.addEventListener("click", () => removePrompt(doc));
  box.append(label, save, close);
  host.appendChild(box);
  return box;
}

/**
 * Save `text` as `filename`. Inside a live tap it shares (phone) or
 * downloads (desktop) right away. After the activation expired it asks for
 * one more tap instead of failing silently.
 */
export function saveTextFile(filename: string, text: string, mime: string): void {
  if (typeof document === "undefined") {
    throw new Error("downloadTextFile requires a document");
  }
  const doc = document;
  const win = globalThis as unknown as Env;
  if (!hasUserActivation(win.navigator)) {
    showSavePrompt(doc, filename, () => saveNow(win, doc, filename, text, mime));
    return;
  }
  saveNow(win, doc, filename, text, mime);
}
