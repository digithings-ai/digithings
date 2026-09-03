'use client';

/**
 * Desk+ digichat popup (#3422) — bottom-right launcher + floating iframe panel.
 * Mirrors digichat `widget.js` (#3421) without loading an external script (CSP).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePlanTier } from '@/lib/use-entitlement';
import {
  buildDigichatEmbedSrc,
  buildPageContextMessage,
  buildThemeMessage,
  canUseDigichatPopup,
  DIGICHAT_READY,
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
  const [iframeSrc, setIframeSrc] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const pageContextSentRef = useRef(false);
  const themeRef = useRef<DigichatPopupTheme>('dark');

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

  const sendPageContext = useCallback(() => {
    if (!config?.pageContext || pageContextSentRef.current) return;
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    const text = extractVisiblePageText();
    try {
      win.postMessage(buildPageContextMessage(text), config.origin);
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
      if (ev.key === 'Escape') setOpen(false);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  if (!config || !entitled) return null;

  const mode = config.mode;

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
        className={[
          'pointer-events-auto fixed right-5 bottom-[5.5rem] z-[2147483000]',
          'h-[min(640px,calc(100vh-7.5rem))] w-[min(400px,calc(100vw-1.5rem))]',
          'overflow-hidden rounded-2xl bg-[#0b0b0c] shadow-[0_16px_48px_rgba(0,0,0,0.28)]',
          open ? 'block' : 'hidden',
        ].join(' ')}
      >
        {iframeSrc ? (
          <iframe
            ref={iframeRef}
            id="digichat-popup-iframe"
            title="digichat"
            src={iframeSrc}
            allow="clipboard-write"
            className="h-full w-full border-0 bg-transparent"
          />
        ) : null}
      </div>
      <button
        id="digichat-popup-launcher"
        type="button"
        data-mode={mode}
        aria-label={open ? 'Close digichat' : 'Open digichat'}
        aria-expanded={open}
        aria-controls="digichat-popup-panel"
        onClick={() => setOpen((v) => !v)}
        style={{ background: config.accent, color: '#06110f' }}
        className={[
          'pointer-events-auto fixed right-5 bottom-5 z-[2147483000]',
          'cursor-pointer border-0 shadow-[0_8px_24px_rgba(0,0,0,0.18)]',
          'transition-[transform,opacity] duration-150 ease-out hover:-translate-y-px',
          mode === 'bar'
            ? 'h-11 min-w-[10rem] rounded-[10px] px-4 text-sm font-semibold'
            : 'h-14 w-14 rounded-full text-[22px] leading-[56px]',
        ].join(' ')}
      >
        {mode === 'bar' ? 'Ask digichat' : '✦'}
      </button>
    </div>
  );
}
