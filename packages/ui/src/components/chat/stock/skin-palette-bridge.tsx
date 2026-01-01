"use client";

import "../../../styles/chat-skin-palette.css";

import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { ComposerPrimitive } from "@assistant-ui/react";
import { ComposerTriggerPopover } from "../gallery-thread/composer-trigger-popover.aui";
import {
  useSkinSlashPalette,
  type DigichatSkinSlash,
  type SkinSlashPalette,
} from "./skin-slash-palette";
import { SkinPaletteContext } from "./skin-palette-context";
import { useEmbedChatPrefsOptional } from "./embed-chat-prefs";

/** Marks the thread composer form the shared palette is anchored to. */
export const SKIN_PALETTE_COMPOSER_ATTR = "data-skin-palette-composer";

function composerForms(root: ParentNode): HTMLFormElement[] {
  return Array.from(root.querySelectorAll("form")).filter(
    (form) =>
      !form.closest("[data-message-id]") &&
      Boolean(form.querySelector('textarea, [contenteditable="true"]')),
  );
}

/** Laid out (not `display: none` or inside a hidden layout branch). */
function isRendered(form: HTMLFormElement): boolean {
  return form.getClientRects().length > 0;
}

/**
 * The thread composer of the skin inside `scope`: a form holding a text
 * input that is not an edit composer inside a message. Layout skins that
 * open the thread in a popover (the assistant modal) portal it out of the
 * scope, and some keep a hidden desktop thread next to the mobile popover
 * one, so the pick is: the composer being typed in, else the last one on
 * screen (in the scope first, then in a popover), else the last in the
 * scope, else the last in a popover.
 */
export function findThreadComposer(scope: HTMLElement): HTMLFormElement | null {
  const inScope = composerForms(scope);
  const portaled = composerForms(scope.ownerDocument).filter(
    (form) =>
      !scope.contains(form) &&
      Boolean(form.closest("[data-radix-popper-content-wrapper]")),
  );
  const active = scope.ownerDocument.activeElement;
  const focused = active
    ? [...inScope, ...portaled].find((form) => form.contains(active))
    : undefined;
  return (
    focused ??
    inScope.filter(isRendered).at(-1) ??
    portaled.filter(isRendered).at(-1) ??
    inScope.at(-1) ??
    portaled.at(-1) ??
    null
  );
}

export type SkinPaletteBridgeProps = {
  /** Product slash wiring from the host. Absent = the skin renders as is. */
  slash?: DigichatSkinSlash | undefined;
  privateMode?: boolean | undefined;
  children: ReactNode;
};

/**
 * Gives any skin the product `/` palette (and `@` tools) without the skin
 * knowing about it. Same commands and submit behaviour as the digichat skin,
 * which wires the palette into its own composer instead.
 *
 * - One `Unstable_TriggerPopoverRoot` around the skin, so whichever
 *   `ComposerPrimitive.Input` the skin renders registers with it.
 * - The popovers portal into the thread composer form, which the stylesheet
 *   makes the positioning box, so they sit right above it like the digichat
 *   palette.
 * - Slash submits (block, pane, force, run) are caught in the capture phase
 *   and never reach the skin's own send handler.
 */
/**
 * The visual prefs a skin that is not digichat reads from its scope:
 * `/density` respaces the messages and `/scrollbar` shows or hides the bars
 * of the skin's scroll surfaces (chat-skin-palette.css). Prefs come through
 * the provider overlay, so a hovered row in the `/` menu previews here too.
 */
function useSkinLook(): { density: string; scrollbars: "always" | "auto" } {
  const chatPrefs = useEmbedChatPrefsOptional()?.prefs;
  return {
    density: chatPrefs?.density ?? "default",
    scrollbars: chatPrefs?.scrollbars ?? "always",
  };
}

/** The look attributes alone, for a skin mounted without the palette. */
function SkinLookScope({ children }: { children: ReactNode }) {
  const { density, scrollbars } = useSkinLook();
  return (
    <div
      data-skin-look-scope=""
      data-skin-density={density}
      data-skin-scrollbars={scrollbars}
      style={{ display: "contents" }}
    >
      {children}
    </div>
  );
}

export function SkinPaletteBridge({
  slash,
  privateMode,
  children,
}: SkinPaletteBridgeProps) {
  const palette = useSkinSlashPalette({ slash, privateMode });
  if (!palette.enabled) return <SkinLookScope>{children}</SkinLookScope>;
  return <SkinPaletteScope palette={palette}>{children}</SkinPaletteScope>;
}

function SkinPaletteScope({
  palette,
  children,
}: {
  palette: SkinSlashPalette;
  children: ReactNode;
}) {
  const scopeRef = useRef<HTMLDivElement | null>(null);
  // `/density` for skins that are not digichat: the scope carries the choice
  // and chat-skin-palette.css respaces the messages under it.
  const { density, scrollbars } = useSkinLook();
  const [anchor, setAnchor] = useState<HTMLFormElement | null>(null);
  const submitRef = useRef(palette.handleSubmit);
  submitRef.current = palette.handleSubmit;
  const anchorRef = useRef<HTMLFormElement | null>(null);
  anchorRef.current = anchor;

  // Skins mount the composer lazily and swap it (welcome vs. thread), so the
  // anchor is re-found after DOM changes, at most once per frame.
  useEffect(() => {
    const scope = scopeRef.current;
    if (!scope) return;
    let frame = 0;
    const find = () => {
      frame = 0;
      const next = findThreadComposer(scope);
      setAnchor((prev) => (prev === next ? prev : next));
    };
    find();
    const observer = new MutationObserver(() => {
      if (!frame) frame = requestAnimationFrame(find);
    });
    // The body, not the scope: a popover-hosted thread mounts in a portal.
    observer.observe(scope.ownerDocument.body, { childList: true, subtree: true });
    // Focus moving between composers (or a breakpoint hiding one) changes
    // which one is live without touching the DOM tree.
    const refind = () => {
      if (!frame) frame = requestAnimationFrame(find);
    };
    scope.ownerDocument.addEventListener("focusin", refind);
    window.addEventListener("resize", refind);
    return () => {
      observer.disconnect();
      scope.ownerDocument.removeEventListener("focusin", refind);
      window.removeEventListener("resize", refind);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  useEffect(() => {
    if (!anchor) return;
    anchor.setAttribute(SKIN_PALETTE_COMPOSER_ATTR, "");
    return () => anchor.removeAttribute(SKIN_PALETTE_COMPOSER_ATTR);
  }, [anchor]);

  // Capture phase on the document, so it runs before the skin's own submit
  // handler (React listens at the root) even for a portaled composer.
  useEffect(() => {
    const onSubmit = (event: Event) => {
      if (!anchorRef.current || event.target !== anchorRef.current) return;
      if (submitRef.current(event)) event.stopPropagation();
    };
    document.addEventListener("submit", onSubmit, true);
    return () => document.removeEventListener("submit", onSubmit, true);
  }, []);

  return (
    <SkinPaletteContext.Provider value={palette}>
      <ComposerPrimitive.Unstable_TriggerPopoverRoot>
        <div
          ref={scopeRef}
          data-skin-palette-scope=""
          data-skin-density={density}
          data-skin-scrollbars={scrollbars}
          style={{ display: "contents" }}
        >
          {children}
        </div>
        {anchor ? createPortal(<SkinPalettePopovers palette={palette} />, anchor) : null}
      </ComposerPrimitive.Unstable_TriggerPopoverRoot>
    </SkinPaletteContext.Provider>
  );
}

function SkinPalettePopovers({ palette }: { palette: SkinSlashPalette }) {
  return (
    <>
      {palette.slash ? (
        <ComposerTriggerPopover
          char="/"
          className="skin-palette"
          adapter={palette.slash.adapter}
          action={palette.slash.action}
          matcher={palette.slash.matcher}
          emptyItemsLabel="No matching commands"
        />
      ) : null}
      {palette.mention ? (
        <ComposerTriggerPopover
          char="@"
          className="skin-palette"
          adapter={palette.mention.adapter}
          directive={palette.mention.directive}
          emptyItemsLabel="No matching tools"
        />
      ) : null}
    </>
  );
}
