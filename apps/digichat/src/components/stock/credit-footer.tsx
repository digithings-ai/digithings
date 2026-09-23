/**
 * The "powered by digichat" credit line.
 *
 * Every surface renders this: the embed/product shell, the baseline preview
 * and any other stock host. It is on unless the config explicitly opts out
 * (`chrome.attribution: false` on a deployment, or `attribution: false` on an
 * embed tenant), so the credit is guaranteed across skins and hosts instead of
 * depending on each surface wiring its own copy (m2147).
 *
 * The embed's own placement rule lives in `lib/embed-ui-flags.ts`
 * (`resolveAttributionPlacement`): opt-in moves the credit to this footer,
 * opt-out leaves the header parenthetical (or nothing, when untitled). This
 * component is the footer half, so it returns null when attribution is off.
 *
 * Placement: in normal flow BELOW the composer, the way every catalog skin
 * places its own "can make mistakes" line — not an absolute overlay. An
 * overlay lost the race with the composer (it painted over the credit once a
 * turn was submitted, and the centered empty-thread composer overlapped it at
 * first paint), so the credit takes real space in the thread's viewport
 * footer and nothing can overflow onto it (m2357).
 *
 * It paints no canvas of its own: it inherits whatever the chat surface
 * paints, so it reads as one surface with the transcript on every skin.
 */

import { cn } from "@/lib/utils";

export function CreditFooter({
  attribution,
  className,
}: {
  attribution: boolean;
  className?: string;
}) {
  if (!attribution) return null;

  return (
    <p className={cn("dc-attribution", className)} data-slot="aui_credit">
      powered by digichat — a{" "}
      <a href="https://digithings.ai" target="_blank" rel="noreferrer noopener">
        digithings
      </a>{" "}
      product.
    </p>
  );
}
