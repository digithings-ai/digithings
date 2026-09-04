'use client';

/**
 * Desk+ digichat popup (#3422 / #3581) — bottom-right launcher + floating iframe.
 * Mirrors digichat `widget.js` (#3421) without loading an external script (CSP).
 * Rectangular “ask digichat” chrome, expand/collapse, HTML page context.
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

  const launcherLabel = open
    ? DIGICHAT_LAUNCHER_CLOSE_LABEL
    : DIGICHAT_LAUNCHER_LABEL;

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
          'pointer-events-auto fixed z-[2147483000] flex flex-col overflow-hidden bg-surface shadow-lg',
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
            className="min-h-0 w-full flex-1 border-0 bg-transparent"
          />
        ) : null}
      </div>
      <button
        id="digichat-popup-launcher"
        type="button"
        data-mode="bar"
        aria-label={open ? 'Close digichat' : 'Open digichat'}
        aria-expanded={open}
        aria-controls="digichat-popup-panel"
        onClick={togglePanel}
        className={[
          'pointer-events-auto fixed right-5 bottom-5 z-[2147483000]',
          'h-11 min-w-[10rem] cursor-pointer rounded-none border border-hair bg-surface',
          'px-4 text-sm font-medium text-ink shadow-lg',
          'transition-[transform,opacity,border-color,background-color] duration-150 ease-out',
          'hover:-translate-y-px hover:border-ink-mute hover:bg-ink/[0.04]',
        ].join(' ')}
      >
        {launcherLabel}
      </button>
    </div>
  );
}
