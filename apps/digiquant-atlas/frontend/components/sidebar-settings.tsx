'use client';

import { createPortal } from 'react-dom';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
} from 'react';
import { Settings } from 'lucide-react';
import { useAppShell } from '@/components/app-shell-context';
import { SettingsContent } from '@/components/settings-content';

const PANEL_W = 280;
const GAP = 8;
/** Above command palette (2000) and mobile overlay */
const PANEL_Z = 10050;

function useClientMounted() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );
}

function panelStyle(
  btn: DOMRect,
  collapsed: boolean,
  vw: number,
  vh: number
): CSSProperties {
  const w = Math.min(PANEL_W, vw - 16);
  if (collapsed) {
    let left = btn.right + GAP;
    if (left + w > vw - GAP) {
      left = btn.left - GAP - w;
    }
    left = Math.max(GAP, Math.min(left, vw - w - GAP));
    let top = btn.top;
    top = Math.max(GAP, Math.min(top, vh - 120));
    return { position: 'fixed' as const, left, top, width: w, zIndex: PANEL_Z };
  }
  const left = Math.max(GAP, Math.min(btn.left, vw - w - GAP));
  const bottom = vh - btn.top + GAP;
  return { position: 'fixed' as const, left, bottom, width: w, zIndex: PANEL_Z };
}

export default function SidebarSettings({ sidebarCollapsed }: { sidebarCollapsed: boolean }) {
  const mounted = useClientMounted();
  const [open, setOpen] = useState(false);
  const [panelStyleState, setPanelStyleState] = useState<CSSProperties | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const { setMobileNavOpen } = useAppShell();

  const updatePosition = useCallback(() => {
    const btn = buttonRef.current;
    if (!btn || !open) return;
    const r = btn.getBoundingClientRect();
    setPanelStyleState(panelStyle(r, sidebarCollapsed, window.innerWidth, window.innerHeight));
  }, [open, sidebarCollapsed]);

  useLayoutEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- measure anchor & sync portaled panel */
    if (!open) {
      setPanelStyleState(null);
      return;
    }
    updatePosition();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [open, sidebarCollapsed, updatePosition]);

  useEffect(() => {
    if (!open) return;
    const onWin = () => updatePosition();
    window.addEventListener('resize', onWin);
    window.addEventListener('scroll', onWin, true);
    return () => {
      window.removeEventListener('resize', onWin);
      window.removeEventListener('scroll', onWin, true);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      const t = e.target as Node;
      if (wrapRef.current?.contains(t)) return;
      if (panelRef.current?.contains(t)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const panel =
    open && mounted && panelStyleState ? (
      <div
        ref={panelRef}
        style={panelStyleState}
        className="rounded-xl border border-border-subtle bg-bg-glass backdrop-blur-xl shadow-glass p-4 max-h-[min(70vh,520px)] overflow-y-auto"
        role="dialog"
        aria-label="Settings"
      >
        <SettingsContent
          onNavigate={() => {
            setOpen(false);
            setMobileNavOpen(false);
          }}
        />
      </div>
    ) : null;

  return (
    <div className="relative" ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Settings"
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`
          flex items-center gap-3 w-full rounded-lg py-3 text-sm font-medium transition-colors
          text-text-secondary hover:text-text-primary hover:bg-white/[0.03]
          ${sidebarCollapsed ? 'md:justify-center md:px-3' : 'px-3'}
          ${open ? 'bg-white/[0.06] text-text-primary' : ''}
        `}
      >
        <Settings size={20} className="shrink-0" />
        <span className={sidebarCollapsed ? 'md:sr-only' : ''}>Settings</span>
      </button>

      {mounted && panel ? createPortal(panel, document.body) : null}
    </div>
  );
}
