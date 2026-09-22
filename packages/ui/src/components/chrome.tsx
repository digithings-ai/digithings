"use client";
/** Shared nav, footer, and module card. Brand + links are passed in so both
 *  marketing apps reuse the same chrome. */
import { useRef, type AnchorHTMLAttributes, type ReactNode } from "react";
import { m, useScroll, useTransform } from "motion/react";
import type { VariantProps } from "class-variance-authority";
import { Emblem } from "./emblems";
import { StackRow } from "./StackLogo";
import { type ModuleNode } from "../data/modules";
import { useMotionSafe } from "../motion/primitives";
import { buttonVariants } from "../ui/button";
import { cn } from "../lib/utils";

export interface NavLink { label: string; href: string; external?: boolean; cta?: boolean; }

/** A labelled set of destinations — a dropdown menu on <NavShell/>'s wide bar,
 *  a labelled section of links in its narrow sheet. A group is a *sibling* type
 *  rather than an optional `items?` on NavLink because a group trigger has no
 *  destination of its own: making `href` optional to model that would widen it
 *  to `string | undefined` for every existing consumer and reader (the
 *  `key={l.href + l.label}` in this file included). A separate interface keeps
 *  `href` required where it belongs and makes "link or group" a real
 *  discriminated choice. */
export interface NavGroup { label: string; items: NavLink[]; }

/** One top-bar entry. `NavLink[]` stays assignable to `NavItem[]`, so every
 *  consumer that passes a flat link array today keeps compiling untouched. */
export type NavItem = NavLink | NavGroup;

/** Discriminates the NavItem union on the one field only a group carries. */
export function isNavGroup(item: NavItem): item is NavGroup {
  return "items" in item;
}

/** The kit's vocabulary for a CTA's dress, taken straight from buttonVariants
 *  so there is exactly one button treatment in the canon — a CTA link is the
 *  same dress as the Button it pairs with, never a parallel class family. */
type ButtonVariant = NonNullable<VariantProps<typeof buttonVariants>["variant"]>;
type ButtonSize = NonNullable<VariantProps<typeof buttonVariants>["size"]>;

/** Absolute or protocol-relative href — never a same-page route. */
const isExternalHref = (href: string) => /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//");

/** Whether `href` names the page the visitor is currently on. Owned here so
 *  every site marks `aria-current` by the same rule: an exact pathname match
 *  only — never an external link, and never a same-page anchor (`/#pipeline`,
 *  `#section`) since several of those share one pathname and would all light
 *  up. Trailing slashes are equivalent (`/docs` ≡ `/docs/`, the static-export
 *  shape). */
export function hrefIsCurrent(href: string, currentPath?: string): boolean {
  if (!currentPath || isExternalHref(href) || href.includes("#")) return false;
  const path = href.split("?")[0] ?? href;
  const norm = (p: string) => (p.length > 1 ? p.replace(/\/+$/, "") : p);
  return norm(path) === norm(currentPath);
}

/** Skip-to-content — visually hidden until keyboard focus, then pinned to the
 *  top-left. Token utilities (the pre-canon app copy is what this replaces);
 *  the consumer owns the target's `id` and focusability. */
export function SkipLink({
  href = "#main",
  children = "Skip to content",
  className,
}: {
  href?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={cn(
        "fixed top-2 left-2 z-[300] -translate-y-[200%] rounded-none bg-[var(--accent)] px-[0.9rem] py-2 font-mono text-[0.72rem] text-[var(--on-accent)] no-underline focus-visible:translate-y-0",
        className,
      )}
    >
      {children}
    </a>
  );
}

export interface CtaLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  href: string;
  /** buttonVariants variant — the single CTA dress vocabulary. */
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** External destination: opens a new tab with the matching rel. */
  external?: boolean;
  /** Optional leading glyph, rendered before the label. */
  icon?: ReactNode;
}

/** A CTA link dressed with the kit's button treatment. The kit shipped a
 *  `<Button>` (a real button) but no link equivalent, so every site hand-rolled
 *  `buttonVariants(...)` at the call site (or invented a `.dc-nav-cta` /
 *  `.dq-cta` class). This is that one treatment, named. */
export function CtaLink({
  href,
  children,
  variant = "default",
  size = "sm",
  external,
  icon,
  className,
  ...rest
}: CtaLinkProps) {
  return (
    <a
      href={href}
      className={cn(buttonVariants({ variant, size }), className)}
      target={external ? "_blank" : undefined}
      rel={external ? "noopener noreferrer" : undefined}
      {...rest}
    >
      {icon}
      {children}
    </a>
  );
}

export interface IconLinkProps
  extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href" | "aria-label"> {
  href: string;
  /** The accessible name — required, because the child is a bare glyph. */
  label: string;
  external?: boolean;
}

/** Icon-only link (the nav tail's GitHub glyph, a mark-only CTA). The kit's
 *  ghost icon-button dress, with the `aria-label` the bare svg needs made
 *  mandatory rather than left to each call site. */
export function IconLink({ href, label, external, className, children, ...rest }: IconLinkProps) {
  return (
    <a
      href={href}
      aria-label={label}
      className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }), className)}
      target={external ? "_blank" : undefined}
      rel={external ? "noopener noreferrer" : undefined}
      {...rest}
    >
      {children}
    </a>
  );
}

export function Footer({
  links,
  meta,
  profiles,
}: {
  links: NavLink[];
  meta: string;
  /** Quiet company-profile row (typically <SocialRow/>). Optional so existing
   *  call sites stay a utility-link strip; socials are a dedicated primitive,
   *  not a fake Connect column. */
  profiles?: ReactNode;
}) {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <nav className="footer-links" aria-label="Footer">
          {links.map((l) => (
            <a key={l.href + l.label} href={l.href} target={l.external ? "_blank" : undefined}
              rel={l.external ? "noopener noreferrer" : undefined}>{l.label}</a>
          ))}
        </nav>
        {profiles}
        <p className="footer-meta">{meta}</p>
      </div>
    </footer>
  );
}

/** The page's last word (canon §08): the module's name at giant scale,
 *  1px hairline outline by default — plus an opt-in scroll-scrubbed glow
 *  sweep. The outline rise/fill is scroll-scrubbed with zero JS via CSS
 *  `animation-timeline: view()` (@supports-gated in site.css); under
 *  reduced motion or without support the name simply stands. The suffix
 *  wears var(--accent), so each app's livery (or the umbrella's ink)
 *  dresses it automatically. aria-hidden: punctuation, not content.
 *
 *  `sweep` (default false — the outline-only ruling stands for every
 *  existing consumer) adds the reference footer's personality moment: an
 *  accent glow passing left→right across the wordmark, scrubbed by the
 *  colophon's own scroll progress (same offsets/transform as
 *  reference/components/footer-reference.tsx). A duplicate overlay span
 *  carries the gradient clipped to its glyphs; reduced motion (and no-JS)
 *  park the band off-screen so no glow travels. Requires a MotionProvider
 *  in the consuming app. */
export function Colophon({
  name,
  suffix,
  sweep = false,
}: {
  name: string;
  suffix?: string;
  sweep?: boolean;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  // useMotionSafe(), not raw useReducedMotion() -- see WordReveal.tsx's fix
  // comment (#2244) for the full hydration-mismatch mechanism this avoids.
  const reduced = !useMotionSafe();
  // 0 = the colophon's top enters the viewport bottom; 1 = scrolled to its
  // end. The band travels off-left → off-right across the middle of that
  // range, so the highlight crosses the wordmark once as you scroll into it.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end end"],
  });
  const sweepPos = useTransform(scrollYProgress, [0.38, 0.96], [120, -20]);
  const backgroundPosition = useTransform(sweepPos, (v) => `${v}% 0`);

  return (
    <div className="colophon" aria-hidden="true" ref={ref}>
      <span className="colo-word">
        {name}
        {suffix ? <b>{suffix}</b> : null}
        {sweep ? (
          <m.span
            className="colo-sweep"
            style={reduced ? undefined : { backgroundPosition }}
          >
            {name}
            {suffix}
          </m.span>
        ) : null}
      </span>
    </div>
  );
}

export function ModuleCard({
  m,
  hrefForModule = (id: string) => `/modules/${id}`,
}: {
  m: ModuleNode;
  /** Host-owned module URL. Defaults to the `/modules/[id]` host contract. */
  hrefForModule?: (id: string) => string;
}) {
  return (
    <a className={`mod-card t-${m.tier}`} href={hrefForModule(m.id)}>
      <div className="mod-card-top">
        <Emblem id={m.emblem} size={26} />
        <span className={`dg-tier t-${m.tier}`}>{m.tier}</span>
      </div>
      <h3>{m.name}</h3>
      <p className="role">{m.role}</p>
      <StackRow items={m.stack.slice(0, 4)} className="stack-row compact" />
    </a>
  );
}
