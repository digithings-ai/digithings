'use client';

/**
 * D8 live preview: DigiChat (DIG-2698).
 *
 * Inline iframe preview of a live DigiChat instance for dashboard pages.
 * Entitlement-gated exactly like the popup: entitled tiers get the iframe,
 * baseline tiers get the upgrade panel and never an iframe (#3662).
 * The iframe origin must stay inside DASHBOARD_DIGICHAT_FRAME_SRC
 * (security-headers.mjs); no wildcard, no new origin in this file.
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
      <section data-digichat-live-preview="upgrade">
        <h2>{DIGICHAT_UPGRADE_TITLE}</h2>
        <p>{DIGICHAT_UPGRADE_BODY}</p>
        <a href={DIGICHAT_UPGRADE_CTA_HREF}>{DIGICHAT_UPGRADE_CTA_LABEL}</a>
      </section>
    );
  }

  return (
    <section data-digichat-live-preview="live">
      <iframe src={src} title="digichat live preview" />
    </section>
  );
}
