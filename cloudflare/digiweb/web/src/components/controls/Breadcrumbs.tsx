/**
 * Breadcrumbs — the wayfinding trail (`nav[aria-label] > ol`). Items are
 * `{ label, href }`; the last item without an `href` renders as the current
 * page (`aria-current="page"`, not a link). Separators are `/` spans,
 * `aria-hidden`. All dress lives in styles/controls-core.css (`.ctl-crumbs*`,
 * import once app-wide); this file carries no Tailwind utilities, so no
 * `@source` line is needed for it.
 */
import type { ReactNode } from "react";

import { cx } from "./cx";

export type Crumb = {
  label: ReactNode;
  href?: string;
};

export function Breadcrumbs({
  items,
  ariaLabel = "Breadcrumb",
  className,
}: {
  items: Crumb[];
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <nav aria-label={ariaLabel} data-slot="breadcrumbs" className={cx("ctl-crumbs", className)}>
      <ol>
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          const isCurrent = isLast && item.href == null;
          return (
            <li key={i}>
              {i > 0 ? (
                <span aria-hidden="true" className="ctl-crumbs-sep">
                  /
                </span>
              ) : null}
              {isCurrent ? (
                <span aria-current="page" className="ctl-crumbs-current">
                  {item.label}
                </span>
              ) : item.href != null ? (
                <a href={item.href} className="ctl-crumbs-link">
                  {item.label}
                </a>
              ) : (
                <span className="ctl-crumbs-link">{item.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
