import { CtaLink, GitHubGlyph, IconLink, SkipLink } from "@digithings/ui";

/**
 * CTA treatments — the one link-as-button vocabulary from @digithings/ui.
 * Before this, each site hand-rolled `buttonVariants(...)` at the call site or
 * invented a local class (`.dc-nav-cta`, `.dq-cta`). `CtaLink` is that
 * treatment, named, and its dress IS `buttonVariants` — a CTA link and the
 * `<Button>` it pairs with are the same button, never a parallel family.
 * `IconLink` is the glyph-only sibling (a required `label` becomes the
 * `aria-label` the bare svg needs). The skip link at the bottom is the
 * keyboard-entry affordance NavShell mounts for a site that opts in.
 */
export function CtaReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// cta treatments"}</p>
      <h2 className="title">One CTA vocabulary.</h2>
      <p className="section-copy">
        <code>CtaLink</code> is a link dressed by the kit&apos;s{" "}
        <code>buttonVariants</code> — <code>default</code> (primary), <code>outline</code>{" "}
        (secondary) and <code>ghost</code> are the same three sizes and variants as{" "}
        <code>Button</code>. It carries the external <code>target</code>/<code>rel</code> pair for
        you, and takes an optional leading glyph. <code>IconLink</code> is the glyph-only link,
        where the accessible name is a required prop rather than left to each call site.
      </p>

      <div className="btn-row">
        <CtaLink href="#">Deploy strategy</CtaLink>
        <CtaLink href="#" variant="outline">
          Read the docs
        </CtaLink>
        <CtaLink href="#" variant="ghost">
          View source
        </CtaLink>
        <IconLink href="https://github.com/digithings-ai" label="digithings on GitHub" external>
          <GitHubGlyph />
        </IconLink>
      </div>

      <p className="section-copy mt-[1.4rem]">
        The skip link is parked off-screen until keyboard focus. This specimen pins it visible
        (<code>relative</code> + <code>translate-y-0</code> overrides) so the treatment is
        inspectable; the production one only appears on Tab.
      </p>
      <div className="mt-[0.6rem] flex">
        <SkipLink className="relative top-auto left-auto translate-y-0" />
      </div>
    </section>
  );
}
