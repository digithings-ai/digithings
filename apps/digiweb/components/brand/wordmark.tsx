/**
 * The canonical digithings wordmark.
 *
 * Same 4×4 mask the brand studio composes and exports
 * (`/brand/studio/wordmark-mask.svg`), drawn in `currentColor`. Static on
 * purpose: the animated build belongs to the studio, not to a page header.
 */
export function BrandWordmark({ className }: { className?: string }) {
  return (
    <span
      className={className ? `brand-wordmark ${className}` : "brand-wordmark"}
      role="img"
      aria-label="digithings"
    />
  );
}
