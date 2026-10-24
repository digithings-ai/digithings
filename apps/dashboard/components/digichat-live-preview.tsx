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
 * The embed mounts on the first open and stays mounted afterwards (the popup
 * does the same, to keep the conversation alive across a close): a frame
 * inside a closed <details> still loads, so an eager iframe would boot the
 * whole digichat app on every dashboard route.
 *
 * Plan-tier handshake (DIG-5139): on digichat:ready the preview posts the
 * theme message and, for entitled tiers with a session token, the plan-tier
 * message — the same handshake the shipped popup performs, built by
 * buildDigichatHandshakeMessages so the two surfaces cannot drift. The embed
 * exchanges the token at /api/plan-proof and sends X-Embed-Plan-Proof on
 * every chat request; the chat route fails closed without it (403
 * plan_tier_required).
 *
 * Two gates, both fail closed:
 *   - the ready message must come from the embed origin AND from this frame
 *     (event.source). The popup's frame is on the same origin, so an origin
 *     check alone would let the popup's ready mint a second proof here.
 *   - in the deployed shell (auth on) the live arm needs a session token.
 *     Without one the embed never gets a proof and every turn answers 403
 *     plan_tier_required: a dead chat surface. An entitled tier without a
 *     session therefore renders nothing at all (not the upgrade panel: the
 *     tier is entitled, the session is missing). The classic shell (auth
 *     off) has no sessions at all; there the preview mirrors the popup,
 *     which shows the same embed for the same entitled tier.
 *
 * Known differences from the popup, on purpose and not yet done: the preview
 * does not fetch the deployed chrome config, does not re-post the theme when
 * the dashboard theme changes, and sends no page context. The popup stays the
 * full chat surface; this is the preview.
 */

import { useContext, useEffect, useMemo, useRef, useState } from 'react';
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
  // The plan proof the chat route needs is minted from the session token, so
  // a deployed shell (auth on) shows the embed only with a session: without
  // one every turn answers 403 plan_tier_required, which is a dead chat
  // surface. The classic shell (auth off) has no sessions at all and the
  // dashboard models the user as entitled; the popup shows the embed there
  // too, and the preview mirrors the popup rather than inventing a third
  // behaviour for the same surface.
  const authEnabled = auth?.authEnabled ?? false;
  const canChat = entitled && (Boolean(accessToken) || !authEnabled);
  const src = useMemo(() => {
    if (!config || !canChat) return null;
    return buildDigichatEmbedSrc(config, readDocumentTheme());
  }, [config, canChat]);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [opened, setOpened] = useState(false);

  // Handshake with the embed (DIG-5139): the frame reports digichat:ready,
  // then the dashboard tells it which theme it runs in and — for entitled
  // tiers with a session — which plan tier it may prove. The embed turns
  // that into the HMAC proof the chat route requires.
  useEffect(() => {
    if (!config || !canChat || !src) return;
    function onMessage(event: MessageEvent) {
      if (event.origin !== config!.origin) return;
      // The popup's frame is on the same origin; only this frame may answer.
      if (event.source !== iframeRef.current?.contentWindow) return;
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
  }, [config, canChat, src, tier, accessToken]);

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

  // Entitled but no session: no proof, no chat. Render nothing rather than a
  // dead chat surface (and not the upgrade panel: the tier is entitled).
  if (!src) return null;

  return (
    <section data-digichat-live-preview="live" className={STRIP_CLASS}>
      <details>
        <summary className={SUMMARY_CLASS} onClick={() => setOpened(true)}>
          digichat live preview
        </summary>
        {opened ? (
          <iframe
            ref={iframeRef}
            src={src}
            title="digichat live preview"
            className={FRAME_CLASS}
          />
        ) : null}
      </details>
    </section>
  );
}
