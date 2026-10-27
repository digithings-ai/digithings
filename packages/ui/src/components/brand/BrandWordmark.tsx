/**
 * The digithings wordmark.
 *
 * Same 4×4 mask the brand studio composes
 * (`packages/brand/studio/wordmark-mask.svg`), drawn in `currentColor`.
 * Each app mirrors that file to `/wordmark-mask.svg` (see
 * `packages/brand/build-studio.py`). Static on purpose: the animated build
 * belongs to the studio, not to a page header.
 */
export function BrandWordmark({
  className,
  label = "digithings",
  mask = "/wordmark-mask.svg",
}: {
  className?: string;
  /** Accessible name. The mark is ink, not text. */
  label?: string;
  /**
   * Mask URL. Apps served under a base path pass the prefixed path; the
   * default is the site root.
   */
  mask?: string;
}) {
  return (
    <span
      className={className ? `brand-wordmark ${className}` : "brand-wordmark"}
      role="img"
      aria-label={label}
      style={{ ["--brand-wordmark" as string]: `url("${mask}")` }}
    />
  );
}
