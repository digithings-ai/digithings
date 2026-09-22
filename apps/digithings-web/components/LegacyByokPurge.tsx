"use client";

import { useEffect } from "react";
import { purgeLegacyApiKey } from "@/lib/providerSettings";

/**
 * Mounted once from the root layout so the legacy `digichat:api_key`
 * localStorage purge runs on every digithings-web page load — not only on
 * pages that historically rendered an in-process session.
 *
 * Neither `/chat` nor `/chat/occ` mount a session widget (they render
 * `ChatEmbedShell`, an iframe to digichat `/embed`), so a returning visitor's
 * stale key from a prior build was never purged on this site's most-visited
 * routes. See #2348.
 */
export function LegacyByokPurge(): null {
  useEffect(() => {
    purgeLegacyApiKey();
  }, []);
  return null;
}
