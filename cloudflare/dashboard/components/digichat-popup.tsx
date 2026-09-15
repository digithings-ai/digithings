'use client';

/**
 * Desk+ digichat popup (#3422) — dashboard adapter around digiweb's shared
 * square-to-panel launcher. This file owns entitlement, embed URL, theme, and
 * page-context messaging; @digithings/web owns all launcher chrome and motion.
 *
 * Baseline (free/brief) sees the same launcher but an upgrade CTA panel with
 * chat disabled (#3662) — never an iframe, so non-entitled tiers never burn
 * turns and never meet the free-3 gate. FX Hub product grantees (the 12x
 * invite path) are the exception: they open the chat, with a desk-equivalent
 * plan proof minted server-side.
 */

import { DigichatLauncher } from '@digithings/web';
import { usePathname } from 'next/navigation';
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
import { useCanAccessProduct, usePlanTier } from '@/lib/use-entitlement';
import {
  buildDigichatEmbedSrc,
  buildPageContextMessage,
  buildPageContextSignature,
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
  PAGE_CONTEXT_RESEND_DEBOUNCE_MS,
  readDigichatPopupConfig,
  readDocumentTheme,
  type DigichatChromeApiResponse,
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
  const canFxHub = useCanAccessProduct('fx_hub');
  const pathname = usePathname();
  const tier = tierOverride ?? sessionTier;
  const auth = useContext(AuthContext);
  const accessToken = auth?.session?.access_token ?? null;
  const baseConfig = useMemo(
    () =>
      configOverride !== undefined ? configOverride : readDigichatPopupConfig(),
    [configOverride],
  );
  const chromeHostKey = baseConfig
    ? `${baseConfig.origin}|${baseConfig.host}`
    : '';
  const [chromeHost, setChromeHost] = useState(chromeHostKey);
  const [chrome, setChrome] = useState<DigichatChromeApiResponse | null>(null);
  if (chromeHost !== chromeHostKey) {
    setChromeHost(chromeHostKey);
    setChrome(null);
  }
  const config = useMemo(() => {
    if (!baseConfig) return null;
    return chrome ? mergeDigichatChromeIntoPopup(baseConfig, chrome) : baseConfig;
  }, [baseConfig, chrome]);

  useEffect(() => {
    if (!baseConfig || configOverride) return;
    let cancelled = false;
    void fetchDigichatChromeConfig(baseConfig.origin, baseConfig.host).then(
      (next) => {
        if (cancelled || !next) return;
        setChrome(next);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [baseConfig, configOverride]);

  // Desk+ opens the iframe; FX Hub product grantees (the 12x invite path) get
  // the same popup — the server mints a desk-equivalent plan proof for them.
  const entitled = canUseDigichatPopup(tier) || canFxHub;
  const [open, setOpen] = useState(false);
  const [iframeSrc, setIframeSrc] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeReadyRef = useRef(false);
  const pageContextSigRef = useRef<string | null>(null);
  const digichatPageContextOffRef = useRef(false);
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
    pageContextSigRef.current = null;
    const nextSrc = buildDigichatEmbedSrc(config, themeRef.current);
    if (nextSrc === iframeSrc) return;
    iframeReadyRef.current = false;
    // A rebuilt iframe is a fresh digichat document: its page-context mode
    // hint (from `digichat:ready`) applies from scratch.
    digichatPageContextOffRef.current = false;
    setIframeSrc(nextSrc);
  }, [open, config, entitled, iframeSrc]);

  const sendPageContext = useCallback(
    (routePathname?: string) => {
      if (!config?.pageContext || digichatPageContextOffRef.current) return;
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      const { html, text } = extractPageContext();
      const signature = buildPageContextSignature(
        routePathname ?? window.location.pathname,
        window.location.search,
        html,
        text,
      );
      if (pageContextSigRef.current === signature) return;
      try {
        win.postMessage(
          buildPageContextMessage(text, { html: html || undefined }),
          config.origin,
        );
        pageContextSigRef.current = signature;
      } catch {
        /* allow retry on next ready */
      }
    },
    [config],
  );

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

  // Change-based page context: resend while open only when the route/query or
  // the sanitized content signature changes (data refresh, filter change, tab
  // switch). The signature was reset on open, so the first post still happens
  // once per open; unchanged signatures are dropped inside `sendPageContext`.
  useEffect(() => {
    if (!config?.pageContext || !open || !entitled) return;
    if (digichatPageContextOffRef.current) return;
    const root = document.querySelector('main') ?? document.body;
    let timer: number | null = null;
    const schedule = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        timer = null;
        if (iframeReadyRef.current && !digichatPageContextOffRef.current) {
          sendPageContext(pathname);
        }
      }, PAGE_CONTEXT_RESEND_DEBOUNCE_MS);
    };
    const observer = new MutationObserver(schedule);
    observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    window.addEventListener('popstate', schedule);
    schedule();
    return () => {
      observer.disconnect();
      window.removeEventListener('popstate', schedule);
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [config, open, entitled, pathname, sendPageContext]);

  useEffect(() => {
    if (!config || !iframeSrc) return;
    function onMessage(ev: MessageEvent) {
      if (ev.origin !== config!.origin) return;
      const data = ev.data as { type?: string; pageContext?: string } | null;
      if (!data || data.type !== DIGICHAT_READY) return;
      iframeReadyRef.current = true;
      if (data.pageContext === 'off') {
        digichatPageContextOffRef.current = true;
      }
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
      if (open && !digichatPageContextOffRef.current) sendPageContext();
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
