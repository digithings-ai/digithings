'use client';

/**
 * Desk+ digichat popup (#3422 / #3581 / #3587) — bottom-right launcher + floating iframe.
 * Mirrors digichat `widget.js` (#3421) without loading an external script (CSP).
 * Compact Digi D-mark launcher; hover typewriter “ask digichat”; expand/collapse;
 * HTML page context.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePlanTier } from '@/lib/use-entitlement';
import {
  buildDigichatEmbedSrc,
  buildPageContextMessage,
  buildThemeMessage,
  canUseDigichatPopup,
  DIGICHAT_LAUNCHER_CLOSE_LABEL,
  DIGICHAT_LAUNCHER_LABEL,
  DIGICHAT_READY,
  extractPageHtml,
  extractVisiblePageText,
  readDigichatPopupConfig,
  readDocumentTheme,
  type DigichatPopupConfig,
  type DigichatPopupTheme,
  type PlanTier,
} from '@/lib/digichat-popup';


export {
  canUseDigichatPopup,
  readDigichatPopupConfig,
  buildDigichatEmbedSrc,
} from '@/lib/digichat-popup';

type DigichatPopupProps = {
  /** Test override — production omits and reads session + env. */
  tier?: PlanTier;
  config?: DigichatPopupConfig | null;
};

/** D-in-block mark (digithings digi-app) — square chrome, ink via currentColor. */
function DigichatLauncherMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      aria-hidden="true"
      className="shrink-0"
    >
      <rect width="100" height="100" fill="currentColor" opacity="0.12" />
      <g fill="currentColor">
        <path d="M26.135 70.21Q21.118 70.21 17.463 67.773Q13.808 65.337 11.838 60.893Q9.867 56.45 9.867 50.358Q9.867 44.267 11.838 39.823Q13.808 35.38 17.463 32.943Q21.118 30.507 26.135 30.507Q29.217 30.507 31.689 31.653Q34.162 32.8 35.846 34.52Q37.53 36.24 38.175 38.032L37.53 39.537V18.467H43.55V69.35H38.103L37.745 60.75L38.677 61.825Q37.817 64.405 35.989 66.304Q34.162 68.203 31.653 69.207Q29.145 70.21 26.135 70.21ZM26.493 64.477Q29.933 64.477 32.406 62.757Q34.878 61.037 36.204 57.848Q37.53 54.658 37.53 50.358Q37.53 45.915 36.204 42.762Q34.878 39.608 32.37 37.924Q29.862 36.24 26.35 36.24Q21.692 36.24 18.933 40.003Q16.173 43.765 16.173 50.358Q16.173 56.88 18.933 60.678Q21.692 64.477 26.493 64.477Z" />
        <rect x="50" y="18.47" width="43" height="50.88" />
      </g>
    </svg>
  );
}

function useTypewriter(full: string, active: boolean, ms = 26) {
  const [typed, setTyped] = useState('');
  useEffect(() => {
    if (!active) {
      setTyped('');
      return;
    }
    let i = 0;
    setTyped('');
    const id = window.setInterval(() => {
      i += 1;
      setTyped(full.slice(0, i));
      if (i >= full.length) window.clearInterval(id);
    }, ms);
    return () => window.clearInterval(id);
  }, [active, full, ms]);
  return typed;
}

export default function DigichatPopup({
  tier: tierOverride,
  config: configOverride,
}: DigichatPopupProps) {
  const sessionTier = usePlanTier();
  const tier = tierOverride ?? sessionTier;
  const config = useMemo(
    () =>
      configOverride !== undefined ? configOverride : readDigichatPopupConfig(),
    [configOverride],
  );

  const entitled = canUseDigichatPopup(tier);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [iframeSrc, setIframeSrc] = useState('');
  const [launcherHover, setLauncherHover] = useState(false);
  const [launcherFocus, setLauncherFocus] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const pageContextSentRef = useRef(false);
  const themeRef = useRef<DigichatPopupTheme>('dark');

  const revealLabel = open
    ? DIGICHAT_LAUNCHER_CLOSE_LABEL
    : DIGICHAT_LAUNCHER_LABEL;
  const typeActive = !open && (launcherHover || launcherFocus);
  const typed = useTypewriter(revealLabel, typeActive);

  useEffect(() => {
    if (!config || !entitled) return;
    themeRef.current = readDocumentTheme();
    const observer = new MutationObserver(() => {
      const t = readDocumentTheme();
      if (t === themeRef.current) return;
      themeRef.current = t;
      const win = iframeRef.current?.contentWindow;
      if (!win || !open) return;
      win.postMessage(buildThemeMessage(t), config.origin);
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    return () => observer.disconnect();
  }, [config, entitled, open]);

  useEffect(() => {
    if (!open || !config) return;
    pageContextSentRef.current = false;
    setIframeSrc(buildDigichatEmbedSrc(config, themeRef.current));
  }, [open, config]);

  const closePanel = useCallback(() => {
    setOpen(false);
    setExpanded(false);
  }, []);

  const togglePanel = useCallback(() => {
    if (open) {
      setOpen(false);
      setExpanded(false);
    } else {
      setOpen(true);
    }
  }, [open]);

  const sendPageContext = useCallback(() => {
    if (!config?.pageContext || pageContextSentRef.current) return;
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    const text = extractVisiblePageText();
    const html = extractPageHtml();
    try {
      win.postMessage(
        buildPageContextMessage(text, { html: html || undefined }),
        config.origin,
      );
      pageContextSentRef.current = true;
    } catch {
      /* allow retry on next ready */
    }
  }, [config]);

  useEffect(() => {
    if (!config || !open) return;
    function onMessage(ev: MessageEvent) {
      if (ev.origin !== config!.origin) return;
      const data = ev.data as { type?: string } | null;
      if (!data || data.type !== DIGICHAT_READY) return;
      const win = iframeRef.current?.contentWindow;
      if (win) {
        win.postMessage(buildThemeMessage(themeRef.current), config!.origin);
      }
      sendPageContext();
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [config, open, sendPageContext]);

  useEffect(() => {
    if (!open) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key !== 'Escape') return;
      if (expanded) {
        setExpanded(false);
        return;
      }
      closePanel();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, expanded, closePanel]);

  if (!config || !entitled) return null;

  const wide = open || typeActive;

  return (
    <div
      data-digichat-popup="1"
      className="pointer-events-none fixed inset-0 z-[2147483000]"
      aria-live="polite"
    >
      <div
        id="digichat-popup-panel"
        role="dialog"
        aria-label="digichat"
        data-open={open ? '1' : '0'}
        data-expanded={expanded ? '1' : '0'}
        className={[
          'pointer-events-auto fixed z-[2147483000] flex flex-col overflow-hidden',
          'border border-hair bg-[#0a0e0c] shadow-[0_8px_32px_rgba(0,0,0,0.55)]',
          open ? 'flex' : 'hidden',
          expanded
            ? 'inset-3 h-auto w-auto'
            : 'right-5 bottom-[5.5rem] h-[min(640px,calc(100vh-7.5rem))] w-[min(400px,calc(100vw-1.5rem))]',
        ].join(' ')}
      >
        <div className="flex shrink-0 items-center justify-end gap-1 border-b border-hair px-2 py-1">
          <button
            type="button"
            id="digichat-popup-expand"
            aria-label={expanded ? 'Collapse digichat' : 'Expand digichat'}
            aria-pressed={expanded}
            onClick={() => setExpanded((v) => !v)}
            className="cursor-pointer border-0 bg-transparent px-2 py-1 font-mono text-[0.72rem] text-ink-mute hover:text-ink"
          >
            {expanded ? 'collapse' : 'expand'}
          </button>
        </div>
        {iframeSrc ? (
          <iframe
            ref={iframeRef}
            id="digichat-popup-iframe"
            title="digichat"
            src={iframeSrc}
            allow="clipboard-write"
            className="min-h-0 w-full flex-1 border-0 bg-[#0a0e0c]"
          />
        ) : null}
      </div>
      <button
        id="digichat-popup-launcher"
        type="button"
        data-mode="icon"
        data-open={open ? '1' : '0'}
        aria-label={open ? 'Close digichat' : 'Open digichat'}
        aria-expanded={open}
        aria-controls="digichat-popup-panel"
        onClick={togglePanel}
        onMouseEnter={() => setLauncherHover(true)}
        onMouseLeave={() => setLauncherHover(false)}
        onFocus={() => setLauncherFocus(true)}
        onBlur={() => setLauncherFocus(false)}
        className={[
          'pointer-events-auto fixed right-5 bottom-5 z-[2147483000]',
          'flex h-11 items-center gap-2 rounded-none border-2 border-[#3dd6c4]',
          'bg-[#0a0e0c] text-[#eceef0] shadow-[0_4px_20px_rgba(61,214,196,0.35)]',
          'cursor-pointer overflow-hidden',
          'transition-[width,padding,transform,box-shadow] duration-150 ease-out',
          'hover:-translate-y-px hover:shadow-[0_6px_24px_rgba(61,214,196,0.5)]',
          'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3dd6c4]',
          wide ? 'w-auto min-w-[11rem] px-3' : 'w-11 justify-center px-0',
        ].join(' ')}
      >
        <DigichatLauncherMark size={22} />
        {open ? (
          <span
            data-testid="digichat-launcher-label"
            className="font-mono text-[0.78rem] tracking-tight text-[#3dd6c4]"
          >
            {DIGICHAT_LAUNCHER_CLOSE_LABEL}
          </span>
        ) : typeActive ? (
          <span
            data-testid="digichat-launcher-label"
            className="inline-flex min-w-[7.5rem] items-center font-mono text-[0.78rem] tracking-tight text-[#eceef0]"
          >
            {typed}
            <span
              aria-hidden="true"
              className="ml-0.5 inline-block h-[0.9em] w-[0.45em] animate-pulse bg-[#3dd6c4]"
            />
          </span>
        ) : null}
      </button>
    </div>
  );
}
