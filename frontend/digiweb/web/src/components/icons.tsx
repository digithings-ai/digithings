/**
 * Brand/interface icon primitives shared across the marketing sites and the
 * reference. Each is a pure className-passthrough SVG: it applies NO Tailwind
 * utilities of its own, so it needs no `@source` line — the call-site
 * className is scanned by the consuming app. Colours come from `currentColor`,
 * so an icon inherits ink in chrome and accent inside a livery scope.
 */
import { type SVGProps } from "react";

/**
 * GitHubGlyph — the simplified GitHub octocat mark. Inlined byte-identically
 * (viewBox 0 0 24 24, the same `d`) in digithings.ai's DtNav, digiquant.io's
 * SiteNav and CloneRepoButton, and the nav-shell reference specimen until
 * #1436 promoted it here. Defaults to 18×18 in `currentColor`; pass a
 * `className` (or any svg attr — width/height override the defaults) at the
 * call site. Distinct from the symbols catalog's `Glyph name="github"`, which
 * draws the fuller official Simple Icons path.
 */
export function GitHubGlyph({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="currentColor"
      aria-hidden="true"
      className={className}
      {...props}
    >
      <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17 4.7 18 5 18 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z" />
    </svg>
  );
}
