"use client";

/**
 * DigichatLauncher — the reusable corner entry point for embedded digichat.
 *
 * Idle is a 30px square carrying the canonical compact terminal mark. Hover or
 * keyboard focus types `digichat` one character at a time without changing the
 * control's height or border. Opening replaces that square in place with a chat
 * panel that expands in two steps from the same corner: first sideways into a
 * composer-height bar, then upward to full height. The transparent backdrop,
 * header close button, and Escape key all dismiss it, reversing both steps.
 *
 * The launcher portals to document.body by default so a backdrop-filter or
 * transformed app shell cannot trap its fixed positioning. Reference specimens
 * can set `portal={false}` to contain it inside a positioned stage.
 *
 * Import `@digithings/web/styles/digichat-launcher.css` once in the app shell.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { TerminalMark } from "../symbols/terminal-marks";

const WORDMARK = "digichat";
const TYPE_MS = 48;
/** Must match the close animation in styles/digichat-launcher.css. */
const CLOSE_MS = 340;

const subscribeToClient = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

export type DigichatLauncherProps = {
  /** Embedded chat surface, usually the digichat iframe. */
  children: ReactNode;
  /** Header label inside the expanded panel. */
  title?: ReactNode;
  /** Accessible name for the expanded panel. */
  ariaLabel?: string;
  /** Render into document.body (default) or inside the current container. */
  portal?: boolean;
  /** Start open for demos or controlled previews. */
  defaultOpen?: boolean;
  /** Called after opening or after the close animation completes. */
  onOpenChange?: (open: boolean) => void;
  className?: string;
  /** Optional CSS custom properties such as panel dimensions or offsets. */
  style?: CSSProperties;
};

export function DigichatLauncher({
  children,
  title = "digichat",
  ariaLabel = "digichat",
  portal = true,
  defaultOpen = false,
  onOpenChange,
  className,
  style,
}: DigichatLauncherProps) {
  /* A portal cannot render on the server. useSyncExternalStore supplies a
     hydration-safe client signal without a mount effect whose sole purpose is
     a synchronous state update. */
  const mounted = useSyncExternalStore(
    subscribeToClient,
    getClientSnapshot,
    getServerSnapshot,
  );
  const [open, setOpen] = useState(defaultOpen);
  const [closing, setClosing] = useState(false);
  const [hasOpened, setHasOpened] = useState(defaultOpen);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const typedRef = useRef<HTMLSpanElement>(null);
  const typingTimerRef = useRef<number | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  /* Focus is restored to the trigger on close for keyboard users, but a
     pointer-driven close should leave a bare square rather than a typed
     wordmark — `:focus-visible` is too unreliable here to decide that. */
  const skipFocusTypeRef = useRef(false);
  const pendingReturnRef = useRef<{ type: boolean } | null>(null);

  const stopTyping = () => {
    if (typingTimerRef.current !== null) {
      window.clearTimeout(typingTimerRef.current);
      typingTimerRef.current = null;
    }
  };

  const resetTrigger = () => {
    stopTyping();
    const trigger = triggerRef.current;
    if (!trigger) return;
    trigger.removeAttribute("data-typing");
    if (typedRef.current) typedRef.current.textContent = "d";
  };

  const typeWordmark = () => {
    if (open || closing) return;
    stopTyping();
    const trigger = triggerRef.current;
    const typed = typedRef.current;
    if (!trigger || !typed) return;

    trigger.setAttribute("data-typing", "");
    typed.textContent = "d";
    let length = 1;

    const reveal = () => {
      length += 1;
      typed.textContent = WORDMARK.slice(0, length);
      if (length < WORDMARK.length) {
        typingTimerRef.current = window.setTimeout(reveal, TYPE_MS);
      } else {
        typingTimerRef.current = null;
      }
    };

    typingTimerRef.current = window.setTimeout(reveal, TYPE_MS);
  };

  const openPanel = () => {
    stopTyping();
    setHasOpened(true);
    setOpen(true);
    onOpenChange?.(true);
  };

  const closePanel = useCallback(
    (options?: { typeOnReturn?: boolean }) => {
      if (!open || closing) return;
      pendingReturnRef.current = { type: options?.typeOnReturn === true };
      if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
        setOpen(false);
        onOpenChange?.(false);
        return;
      }
      setClosing(true);
      closeTimerRef.current = window.setTimeout(() => {
        setOpen(false);
        setClosing(false);
        onOpenChange?.(false);
      }, CLOSE_MS);
    },
    [closing, onOpenChange, open],
  );

  /* Focus restoration rides the trigger's own ref callback: it is the one
     moment the node is guaranteed to exist, and focusing an already-focused
     node fires no event, so the typing decision is made here rather than in
     the focus handler. */
  const attachTrigger = (node: HTMLButtonElement | null) => {
    triggerRef.current = node;
    if (!node) return;
    const pending = pendingReturnRef.current;
    if (!pending) return;
    pendingReturnRef.current = null;
    skipFocusTypeRef.current = true;
    node.focus();
    if (pending.type) {
      skipFocusTypeRef.current = false;
      typeWordmark();
      return;
    }
    /* React may dispatch the focus this call produced after the current task,
       so hold the suppression until that has been delivered, then clear any
       typing it started. */
    window.requestAnimationFrame(() => {
      skipFocusTypeRef.current = false;
      resetTrigger();
    });
  };

  useEffect(() => {
    if (!open) return;
    const focusFrame = window.requestAnimationFrame(() => closeRef.current?.focus());
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePanel({ typeOnReturn: true });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [closePanel, open]);

  useEffect(
    () => () => {
      stopTyping();
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
      }
    },
    [],
  );

  const retainPanel = open || closing || hasOpened;
  const launcher = (
    <div
      className={[
        "digichat-launcher",
        portal ? "" : "digichat-launcher--contained",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={style}
    >
      {open ? (
        <button
          type="button"
          className="digichat-launcher__backdrop"
          aria-label="Close digichat"
          tabIndex={-1}
          onClick={() => closePanel()}
        />
      ) : null}
      {retainPanel ? (
        <section
          className={[
            "digichat-launcher__panel",
            closing ? "is-closing" : "",
            !open && !closing ? "is-hidden" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          role="dialog"
          aria-label={ariaLabel}
        >
          <header className="digichat-launcher__header">
            <span>{title}</span>
            <button
              ref={closeRef}
              type="button"
              className="digichat-launcher__close"
              aria-label="Close digichat"
              onClick={() => closePanel()}
            >
              <svg
                viewBox="0 0 24 24"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M6 6l12 12M18 6 6 18" />
              </svg>
            </button>
          </header>
          <div className="digichat-launcher__body">{children}</div>
        </section>
      ) : null}
      {!open && !closing ? (
        <button
          ref={attachTrigger}
          type="button"
          className="digichat-launcher__trigger"
          aria-label="Open digichat"
          aria-expanded="false"
          onMouseEnter={typeWordmark}
          onMouseLeave={resetTrigger}
          onFocus={() => {
            if (skipFocusTypeRef.current) return;
            typeWordmark();
          }}
          onBlur={resetTrigger}
          onClick={openPanel}
        >
          <TerminalMark
            variant="compact"
            size={20}
            className="digichat-launcher__mark"
          />
          <span className="digichat-launcher__word" aria-hidden="true">
            <span ref={typedRef}>d</span>
            <span className="digichat-launcher__cursor" />
          </span>
        </button>
      ) : null}
    </div>
  );

  if (!portal) return launcher;
  if (!mounted) return null;
  return createPortal(launcher, document.body);
}
