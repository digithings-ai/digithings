'use client';

/**
 * Desk+ digichat popup (#3422) — dashboard adapter around digiweb's shared
 * square-to-panel launcher. This file owns entitlement, embed URL, theme, and
 * page-context messaging; @digithings/web owns all launcher chrome and motion.
 */

import { DigichatLauncher } from '@digithings/web';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { usePlanTier } from '@/lib/use-entitlement';
import {
  buildDigichatEmbedSrc,
  buildPageContextMessage,
  buildThemeMessage,
  canUseDigichatPopup,
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

  if (!config || !entitled) return null;

  return (
    <div data-digichat-popup="1" aria-live="polite">
      <DigichatLauncher
        ariaLabel="digichat dashboard assistant"
        onOpenChange={setOpen}
        style={
          {
            '--digichat-launcher-panel-width':
              'min(400px, calc(100vw - 2.5rem))',
            '--digichat-launcher-panel-height':
              'min(640px, calc(100dvh - 2.5rem))',
            zIndex: 2147483000,
          } as CSSProperties
        }
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
      </DigichatLauncher>
    </div>
  );
}
