'use client';

/**
 * D8 live preview: DigiChat (DIG-2698, DIG-5138, DIG-5139).
 *
 * Inline iframe preview of a live DigiChat instance for dashboard pages.
 * Entitlement-gated exactly like the popup: entitled tiers get the iframe,
 * baseline tiers get the upgrade panel and never an iframe (#3662).
 * The iframe origin must stay inside DASHBOARD_DIGICHAT_FRAME_SRC
 * (security-headers.mjs); no wildcard, no new origin in this file.
 *
 * Layout (DIG-5138): the preview is a bounded strip inside the dashboard
 * content column, not a row sibling of <main>. The sibling mount took its
 * max-content width and squeezed the page column to 38px on desktop and 0px
 * on a 390px phone (QA, DIG-5134). The strip is w-full inside the column, so
 * the column keeps its width at 390x844 and 1440x900. The embed is
 * explicitly sized (h-[320px] md:h-[480px]): the browser default was 300x150,
 * which left the embed a sliver of a chat surface.
 *
 * The strip ships collapsed (a native <details>), so the dashboard page is
 * not pushed down on every route; open it for the live embed. On a phone the
 * chat path stays the DigiChat popup, which supports mobile fullscreen.
 *
 * Plan-tier handshake (DIG-5139): on digichat:ready the preview posts the
 * theme message and, for entitled tiers with a session token, the plan-tier
 * message — the same handshake the shipped popup performs, built by
 * buildDigichatHandshakeMessages so the two surfaces cannot drift. The embed
 * exchanges the token at /api/plan-proof and sends X-Embed-Plan-Proof on
 * every chat request; the chat route fails closed without it (403
 * plan_tier_required).
 */

import { useContext, useEffect, useMemo, useRef } from 'react';
import { buttonVariants } from '@digithings/ui/ui';
import { AuthContext } from '@/lib/auth-context';
import { usePlanTier } from '@/lib/use-entitlement';
import {
  buildDigichatEmbedSrc,
  buildDigichatHandshakeMessages,
  canUseDigichatPopup,
  DIGICHAT_READY,
  DIGICHAT_UPGRADE_BODY,
  DIGICHAT_UPGRADE_CTA_HREF,
  DIGICHAT_UPGRADE_CTA_LABEL,
  DIGICHAT_UPGRADE_TITLE,
  readDigichatPopupConfig,
  readDocumentTheme,
  type DigichatPopupConfig,
  type PlanTier,
} from '@/lib/digichat-popup';

/** The strip fills the content column; it never takes a width of its own. */
const STRIP_CLASS = 'w-full border-b border-hair px-3 py-2';

/** Disclosure summary, in the house strip style (see tui-recorded-frames). */
const SUMMARY_CLASS =
  'text-[10px] font-medium uppercase tracking-widest text-ink-mute';

/** The embed is sized here; the browser default (300x150) clipped it. */
const FRAME_CLASS = 'h-[320px] w-full max-w-[640px] border-0 md:h-[480px]';

type DigichatLivePreviewProps = {
  /** Test override — production omits and reads session + env. */
  tier?: PlanTier;
  config?: DigichatPopupConfig | null;
};

export default function DigichatLivePreview({
  tier: tierOverride,
  config: configOverride,
}: DigichatLivePreviewProps) {
  const sessionTier = usePlanTier();
  const tier = tierOverride ?? sessionTier;
  const auth = useContext(AuthContext);
  const accessToken = auth?.session?.access_token ?? null;
  const config = useMemo(
    () =>
      configOverride !== undefined ? configOverride : readDigichatPopupConfig(),
    [configOverride],
  );
  const entitled = canUseDigichatPopup(tier);
  const src = useMemo(() => {
    if (!config || !entitled) return null;
    return buildDigichatEmbedSrc(config, readDocumentTheme());
  }, [config, entitled]);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Handshake with the embed (DIG-5139): the frame reports digichat:ready,
  // then the dashboard tells it which theme it runs in and — for entitled
  // tiers with a session — which plan tier it may prove. The embed turns
  // that into the HMAC proof the chat route requires.
  useEffect(() => {
    if (!config || !entitled || !src) return;
    function onMessage(event: MessageEvent) {
      if (event.origin !== config!.origin) return;
      const data = event.data as { type?: string } | null;
      if (!data || data.type !== DIGICHAT_READY) return;
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      for (const message of buildDigichatHandshakeMessages({
        tier,
        accessToken,
        theme: readDocumentTheme(),
      })) {
        win.postMessage(message, config!.origin);
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [config, entitled, src, tier, accessToken]);

  if (!config) return null;

  if (!entitled) {
    return (
      <section data-digichat-live-preview="upgrade" className={STRIP_CLASS}>
        <details>
          <summary className={SUMMARY_CLASS}>
            digichat live preview · desk feature
          </summary>
          <div className="mt-2 flex flex-col gap-3">
            <h2 className="text-sm font-medium">{DIGICHAT_UPGRADE_TITLE}</h2>
            <p className="text-sm opacity-70">{DIGICHAT_UPGRADE_BODY}</p>
            <a
              href={DIGICHAT_UPGRADE_CTA_HREF}
              className={`${buttonVariants({ variant: 'link' })} h-auto justify-start px-0 text-sm font-medium underline`}
            >
              {DIGICHAT_UPGRADE_CTA_LABEL}
            </a>
          </div>
        </details>
      </section>
    );
  }

  if (!src) return null;

  return (
    <section data-digichat-live-preview="live" className={STRIP_CLASS}>
      <details>
        <summary className={SUMMARY_CLASS}>digichat live preview</summary>
        <iframe
          ref={iframeRef}
          src={src}
          title="digichat live preview"
          className={FRAME_CLASS}
        />
      </details>
    </section>
  );
}
