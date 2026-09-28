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

/** Google “G” — four brand fills so the mark reads at 18px. Decorative. */
export function GoogleGlyph({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      aria-hidden="true"
      className={className}
      {...props}
    >
      <path
        fill="#4285F4" // canon-allow: Google brand blue (official G mark)
        d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.4h6.5c-.3 1.5-1.1 2.7-2.4 3.5v2.9h3.8c2.3-2.1 3.6-5.2 3.6-8.5z"
      />
      <path
        fill="#34A853" // canon-allow: Google brand green (official G mark)
        d="M12 24c3.2 0 5.9-1.1 7.9-2.9l-3.8-2.9c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.3v3c2 4 6.1 6.6 10.7 6.6z"
      />
      <path
        fill="#FBBC05" // canon-allow: Google brand yellow (official G mark)
        d="M5.3 14.4c-.2-.7-.4-1.5-.4-2.4s.1-1.7.4-2.4V6.6H1.3C.5 8.2 0 10 0 12s.5 3.8 1.3 5.4l4-3z"
      />
      <path
        fill="#EA4335" // canon-allow: Google brand red (official G mark)
        d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4C17.9 1.2 15.2 0 12 0 7.4 0 3.3 2.6 1.3 6.6l4 3c.9-2.9 3.6-4.8 6.7-4.8z"
      />
    </svg>
  );
}

/** LinkedIn “in” mark. currentColor so it tracks ink. Decorative. */
export function LinkedInGlyph({ className, ...props }: SVGProps<SVGSVGElement>) {
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
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  );
}

/** X mark. currentColor so it tracks ink. Decorative. */
export function XGlyph({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="currentColor"
      aria-hidden="true"
      className={className}
      {...props}
    >
      <path d="M18.2 2.3h3.3l-7.2 8.3 8.5 11.2h-6.6l-4.7-6.2-5.4 6.2H2.7l7.8-8.8L1.3 2.3h6.8l4.3 5.6 5.8-5.6zm-1.2 17.5h1.8L7.1 4.1H5.1l11.9 15.7z" />
    </svg>
  );
}
