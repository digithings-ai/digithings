"use client";

/**
 * Shared "powered by digichat" branding line.
 *
 * Every skin renders this same component at the bottom of the page at all
 * times — empty thread included. It is branding, not a disclaimer: the
 * watermark stays visible from the very beginning. (Catalog products gate
 * their own "can make mistakes" line on the first message; ours never
 * gates.) Parents do the pinning: an absolute bottom wrapper in empty
 * states, the sticky viewport footer once messages exist. One component
 * (not per-skin copies) keeps the branding identical on every skin we
 * ship.
 *
 * It paints no canvas of its own: tiny centered text inheriting the surface
 * color at reduced opacity, no border or separator. It returns null when the
 * host opted out (`chrome.attribution: false` / embed `attribution: false`),
 * read from `SkinChromeProvider` (default on without a provider).
 */

import type { FC } from "react";
import { cn } from "@/lib/utils";
import { useAttribution } from "./skin-chrome";

export const SKIN_CREDIT_TEXT = "powered by digichat — a digithings product.";

export const SkinCredit: FC<{
  className?: string;
  /**
   * Explicit override for surfaces with no SkinChromeProvider — the embed's
   * gate/paywall branch, which resolved placement itself. Omit everywhere
   * else to read the host's resolved `attribution` from context.
   */
  attribution?: boolean;
}> = ({ className, attribution }) => {
  const fromContext = useAttribution();
  if (attribution !== undefined ? !attribution : !fromContext) return null;

  return (
    <p
      data-testid="skin-credit"
      data-slot="aui_credit"
      className={cn(
        "pt-0.5 text-center text-xs leading-4 opacity-60",
        className,
      )}
    >
      powered by digichat — a{" "}
      <a
        href="https://digithings.ai"
        target="_blank"
        rel="noreferrer noopener"
        className="pointer-events-auto font-medium text-primary underline-offset-2 hover:underline"
      >
        digithings
      </a>{" "}
      product.
    </p>
  );
};
