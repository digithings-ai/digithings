'use client';

/**
 * D8 live preview: DigiChat (DIG-2698).
 *
 * Inline iframe preview of a live DigiChat instance for dashboard pages.
 * Entitlement-gated exactly like the popup: entitled tiers get the iframe,
 * baseline tiers get the upgrade panel and never an iframe (#3662).
 * The iframe origin must stay inside DASHBOARD_DIGICHAT_FRAME_SRC
 * (security-headers.mjs); no wildcard, no new origin in this file.
 *
 * The section is a flex-row sibling of <main>, so on a phone (390px) the
 * iframe's 300px intrinsic width squeezed the page column to 90px (measured
 * 22 Oct 2026). The preview is therefore desktop-only: `hidden md:block`.
 * Desktop pixels are unchanged, and the phone keeps the DigiChat popup.
 * Both branches are desktop-only on purpose: the section is a row sibling of
 * <main>, so any branch left visible on a 390px phone takes its width out of
 * the page column. The upgrade branch carries the same text width as the
 * iframe, so hiding only the iframe would not give the phone its column back.
 */

import { useMemo } from 'react';
import { usePlanTier } from '@/lib/use-entitlement';
import {
  buildDigichatEmbedSrc,
  canUseDigichatPopup,
  DIGICHAT_UPGRADE_BODY,
  DIGICHAT_UPGRADE_CTA_HREF,
  DIGICHAT_UPGRADE_CTA_LABEL,
  DIGICHAT_UPGRADE_TITLE,
  readDigichatPopupConfig,
  readDocumentTheme,
  type DigichatPopupConfig,
  type PlanTier,
} from '@/lib/digichat-popup';

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
  const config = useMemo(
    () =>
      configOverride !== undefined ? configOverride : readDigichatPopupConfig(),
    [configOverride],
  );
  const src = useMemo(() => {
    if (!config || !canUseDigichatPopup(tier)) return null;
    return buildDigichatEmbedSrc(config, readDocumentTheme());
  }, [tier, config]);
  if (!config) return null;

  if (src === null) {
    return (
      <section data-digichat-live-preview="upgrade" className="hidden md:block">
        <h2>{DIGICHAT_UPGRADE_TITLE}</h2>
        <p>{DIGICHAT_UPGRADE_BODY}</p>
        <a href={DIGICHAT_UPGRADE_CTA_HREF}>{DIGICHAT_UPGRADE_CTA_LABEL}</a>
      </section>
    );
  }

  return (
    <section data-digichat-live-preview="live" className="hidden md:block">
      <iframe src={src} title="digichat live preview" />
    </section>
  );
}
