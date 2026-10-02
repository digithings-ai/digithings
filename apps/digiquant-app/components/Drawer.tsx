'use client';

import { useEffect, useRef, type ReactNode } from 'react';

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])';

/**
 * Dossier drawer — right-side slide-in Window-style panel (e.g. ticker dossier).
 * Esc or backdrop closes; focus moves in on open, is trapped with Tab, and returns to the opener on close.
 */
export function Drawer({ open, onClose, no = '00', label, right, children }: {
  open: boolean;
  onClose: () => void;
  no?: string;
  label: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const opener = useRef<Element | null>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    const el = ref.current;
    el?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); close.current(); return; }
      if (e.key !== 'Tab' || !el) return;
      const f = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!f.length) { e.preventDefault(); return; }
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === el)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', key, true);
    return () => {
      document.removeEventListener('keydown', key, true);
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="drawer-wrap">
      <div className="drawer-back" onClick={onClose} aria-hidden="true" />
      <aside ref={ref} className="drawer win" role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
        <header className="win-bar">
          <span className="ey">{no} / {label}</span>
          <span>{right}<button type="button" className="drawer-x" onClick={onClose} aria-label="Close">esc ✕</button></span>
        </header>
        <div className="win-body">{children}</div>
      </aside>
    </div>
  );
}
