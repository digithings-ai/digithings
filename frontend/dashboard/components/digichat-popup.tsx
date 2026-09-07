'use client';

/**
 * Desk+ digichat popup (#3422) — dashboard adapter around digiweb's shared
 * square-to-panel launcher. This file owns entitlement, embed URL, theme, and
 * page-context messaging; @digithings/web owns all launcher chrome and motion.
 *
 * Baseline (free/brief) sees the same launcher but an upgrade CTA panel with
 * chat disabled (#3662) — never an iframe, so non-entitled tiers never burn
 * turns and never meet the free-3 gate.
 */

import { DigichatLauncher } from '@digithings/web';
import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { AuthContext } from '@/lib/auth-context';
import { usePlanTier } from '@/lib/use-entitlement';
import {
  buildDigichatEmbedSrc,
  buildPageContextMessage,
  buildPlanTierMessage,
  buildThemeMessage,
  canUseDigichatPopup,
  DIGICHAT_READY,
  DIGICHAT_UPGRADE_BODY,
  DIGICHAT_UPGRADE_CTA_HREF,
  DIGICHAT_UPGRADE_CTA_LABEL,
  DIGICHAT_UPGRADE_TITLE,
  extractPageContext,
  fetchDigichatChromeConfig,
  mergeDigichatChromeIntoPopup,
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
  const auth = useContext(AuthContext);
  const accessToken = auth?.session?.access_token ?? null;
  const baseConfig = useMemo(
    () =>
      configOverride !== undefined ? configOverride : readDigichatPopupConfig(),
    [configOverride],
  );
  const [config, setConfig] = useState<DigichatPopupConfig | null>(baseConfig);

  useEffect(() => {
    setConfig(baseConfig);
    if (!baseConfig || configOverride) return;
    let cancelled = false;
    void fetchDigichatChromeConfig(baseConfig.origin, baseConfig.host).then(
      (chrome) => {
        if (cancelled || !chrome) return;
        setConfig(mergeDigichatChromeIntoPopup(baseConfig, chrome));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [baseConfig, configOverride]);

  const entitled = canUseDigichatPopup(tier);
  const [open, setOpen] = useState(false);
  const [iframeSrc, setIframeSrc] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeReadyRef = useRef(false);
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
    if (!open || !config || !entitled) return;
    pageContextSentRef.current = false;
    const nextSrc = buildDigichatEmbedSrc(config, themeRef.current);
    if (nextSrc === iframeSrc) return;
    iframeReadyRef.current = false;
    setIframeSrc(nextSrc);
  }, [open, config, entitled, iframeSrc]);

  const sendPageContext = useCallback(() => {
    if (!config?.pageContext || pageContextSentRef.current) return;
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    const { html, text } = extractPageContext();
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

  // A closed launcher retains its iframe so the conversation survives. On
  // reopen, refresh the theme and page context without waiting for another
  // `digichat:ready` event (the retained document will not emit one).
  useEffect(() => {
    if (!config || !open || !iframeReadyRef.current) return;
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    win.postMessage(buildThemeMessage(themeRef.current), config.origin);
    sendPageContext();
  }, [config, open, sendPageContext]);

  useEffect(() => {
    if (!config || !iframeSrc) return;
    function onMessage(ev: MessageEvent) {
      if (ev.origin !== config!.origin) return;
      const data = ev.data as { type?: string } | null;
      if (!data || data.type !== DIGICHAT_READY) return;
      iframeReadyRef.current = true;
      const win = iframeRef.current?.contentWindow;
      if (win) {
        win.postMessage(buildThemeMessage(themeRef.current), config!.origin);
        // Send authenticated plan tier (#3662): the iframe fetches an HMAC-
        // signed proof from /api/plan-proof and includes it in X-Embed-Plan-Proof.
        // Raw X-Embed-Plan-Tier headers are NEVER trusted by the chat route.
        if (entitled && accessToken) {
          win.postMessage(
            buildPlanTierMessage(tier, accessToken),
            config!.origin,
          );
        }
      }
      if (open) sendPageContext();
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [config, iframeSrc, open, sendPageContext, entitled, tier, accessToken]);

  if (!config) return null;

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
        {entitled ? (
          iframeSrc ? (
            <iframe
              ref={iframeRef}
              id="digichat-popup-iframe"
              title="digichat"
              src={iframeSrc}
              allow="clipboard-write"
              className="h-full w-full border-0 bg-transparent"
            />
          ) : null
        ) : (
          <div
            data-testid="digichat-upgrade-cta"
            className="flex h-full flex-col justify-center gap-3 p-6"
          >
            <p className="text-sm font-medium">{DIGICHAT_UPGRADE_TITLE}</p>
            <p className="text-sm opacity-70">{DIGICHAT_UPGRADE_BODY}</p>
            <a
              href={DIGICHAT_UPGRADE_CTA_HREF}
              className="text-sm font-medium underline underline-offset-4"
            >
              {DIGICHAT_UPGRADE_CTA_LABEL}
            </a>
          </div>
        )}
      </DigichatLauncher>
    </div>
  );
}
