import type { ReactNode } from "react";

import { cn } from "../lib/utils";

/**
 * LayoutLines — the persistent page geometry (D1, #4429).
 *
 * A fixed, full-viewport-height pair of dashed vertical hairlines at the
 * container's edges, mounted once per page and `pointer-events-none`. Every
 * section then sits between them, which is what makes a long page read as one
 * built object rather than a stack of bordered boxes. Without it the only
 * vertical structure on the page is whatever each section draws for itself.
 *
 * Technique read out of launch-ui's `components/ui/layout-lines.tsx` (MIT) and
 * re-expressed in this kit's tokens and width register. The width comes from
 * `--frame-w` plus a gutter on each side, the same register the document
 * grammar uses.
 *
 * Renders nothing meaningful to AT and is `aria-hidden` by construction (an
 * empty decorative element). `fixed` + `inset-0` means it does not scroll,
 * which is the point: the rules are a property of the viewport, not the page.
 *
 * The rules used to land flush on the column, so text ran straight up to them.
 * `--line-pad` pushes the pair *outward* from the content: the inner hairline
 * grows by the gutter on each side while every section keeps its own
 * `--page-pad`, which is what gives the page air inside its own edges. So the
 * rails sit one gutter outside the content column rather than on it.
 *
 * They deliberately do NOT meet the section dividers. `line-t` / `line-b` on a
 * section are full-bleed by design, and those full-width rules are part of the
 * page's document feel; making them stop at the rails would turn every band
 * into a framed box. Two roles, two weights: the dividers separate sections,
 * the rails are a fixed vertical guide that the dividers cross. The rails draw
 * at `--hair-2` because at `--hair` they were invisible — see the note beside
 * `line-y` in web-theme.css.
 */
export function LayoutLines({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none fixed inset-0 top-0 z-0 overflow-hidden", className)}
    >
      <div
        className="mx-auto h-full w-full max-w-[calc(var(--frame-w)+2*var(--line-pad,0px))] line-y line-dashed"
        style={{ ["--line-pad" as string]: "var(--page-pad)" }}
      />
    </div>
  );
}

/**
 * MockupFrame + Mockup — the two-layer product artefact (D1, #4429).
 *
 * A `glow`/gradient frame at one depth holding a surface at another, with the
 * inner surface carrying the drop shadow. That layering is what gives a product
 * shot depth; a bare screenshot inside a border reads flat. Pair with <Glow/>
 * behind it and `fade-bottom` on the section.
 *
 * Technique read out of launch-ui's `components/ui/mockup.tsx` (MIT), ported to
 * this kit's tokens (`--hair`, `--surface`) and to zero radius, matching the
 * canon's flat-corner rule.
 */
export function MockupFrame({
  size = "small",
  className,
  children,
}: {
  /** Frame padding — the visible "bezel" around the mockup. */
  size?: "small" | "large";
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "relative z-10 overflow-hidden bg-hair",
        size === "small" ? "p-[0.5rem]" : "p-[1rem]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Mockup({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "relative z-10 overflow-hidden border border-hair bg-surface shadow-[0_20px_50px_-12px_rgba(0,0,0,0.45)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * Glow — the light source behind a hero artefact (D1, #4429).
 *
 * Two stacked radial ellipses at different scales and opacities, so the falloff
 * is not a single flat wash. `absolute` and `pointer-events-none`; the parent
 * must be `relative`. Accent-tinted, so each app's livery (or the umbrella's
 * neutral ink) dresses it automatically.
 *
 * Technique read out of launch-ui's `components/ui/glow.tsx` (MIT). Their
 * version hardcodes `--brand`; this one reads `--accent`, which digithings.ai
 * already collapses to neutral ink in its own sheet — so the same component
 * gives digiquant.io a green wash and us a white one.
 */
export function Glow({
  variant = "top",
  className,
}: {
  variant?: "top" | "above" | "bottom" | "below" | "center";
  className?: string;
}) {
  const position =
    variant === "above"
      ? "-top-[128px]"
      : variant === "bottom"
        ? "bottom-0"
        : variant === "below"
          ? "-bottom-[128px]"
          : variant === "center"
            ? "top-[50%]"
            : "top-0";
  const centered = variant === "center" ? "-translate-y-1/2" : undefined;
  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none absolute w-full", position, className)}
    >
      <div
        className={cn(
          "absolute left-1/2 h-[256px] w-[60%] -translate-x-1/2 scale-[2.5] rounded-[50%] opacity-20 sm:h-[512px]",
          centered,
        )}
        style={{
          backgroundImage:
            "radial-gradient(ellipse at center, color-mix(in srgb, var(--accent) 50%, transparent) 10%, transparent 60%)",
        }}
      />
      <div
        className={cn(
          "absolute left-1/2 h-[128px] w-[40%] -translate-x-1/2 scale-[2] rounded-[50%] opacity-20 sm:h-[256px]",
          centered,
        )}
        style={{
          backgroundImage:
            "radial-gradient(ellipse at center, color-mix(in srgb, var(--accent) 30%, transparent) 10%, transparent 60%)",
        }}
      />
    </div>
  );
}
