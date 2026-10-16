/**
 * SSR tests for the chrome CTA treatments: <CtaLink/>, <IconLink/> and
 * <SkipLink/>. The point of these components is that they reuse the kit's
 * `buttonVariants` rather than inventing a parallel CTA class family, so the
 * dress assertions name the buttonVariants tokens directly — if CtaLink ever
 * grows its own vocabulary this suite fails alongside the canon guard.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CtaLink, IconLink, SkipLink } from "./chrome";

describe("CtaLink — dress comes from buttonVariants", () => {
  it("defaults to the primary (default) button dress", () => {
    const html = renderToStaticMarkup(<CtaLink href="/chat">Ask digichat</CtaLink>);
    expect(html).toContain("bg-primary");
    expect(html).toContain("text-primary-foreground");
    expect(html).toContain("h-7"); // size "sm" from buttonVariants
    expect(html).toContain("Ask digichat");
  });

  it("maps variant/size straight through to the button vocabulary", () => {
    const outline = renderToStaticMarkup(
      <CtaLink href="/docs" variant="outline">
        Docs
      </CtaLink>,
    );
    expect(outline).toContain("border-border");
    expect(outline).toContain("bg-background");

    const ghost = renderToStaticMarkup(
      <CtaLink href="/docs" variant="ghost" size="xs">
        Docs
      </CtaLink>,
    );
    expect(ghost).toContain("hover:bg-muted");
    expect(ghost).toContain("h-6"); // size "xs"
  });

  it("opens external destinations in a new tab with the matching rel", () => {
    const html = renderToStaticMarkup(
      <CtaLink href="https://github.com/digithings-ai" external>
        GitHub
      </CtaLink>,
    );
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("does not add target/rel to an internal destination", () => {
    const html = renderToStaticMarkup(<CtaLink href="/docs">Docs</CtaLink>);
    expect(html).not.toContain('target="_blank"');
    expect(html).not.toContain("noopener");
  });

  it("renders an optional leading icon before the label", () => {
    const html = renderToStaticMarkup(
      <CtaLink href="/chat" icon={<span data-slot="mark">◐</span>}>
        Ask digichat
      </CtaLink>,
    );
    expect(html).toContain('data-slot="mark"');
    expect(html.indexOf('data-slot="mark"')).toBeLessThan(html.indexOf("Ask digichat"));
  });
});

describe("IconLink — required accessible name", () => {
  it("carries the label as aria-label on the ghost icon-button dress", () => {
    const html = renderToStaticMarkup(
      <IconLink href="https://github.com/digithings-ai" label="digithings on GitHub" external>
        <svg aria-hidden="true" />
      </IconLink>,
    );
    expect(html).toContain('aria-label="digithings on GitHub"');
    expect(html).toContain("size-7"); // buttonVariants size "icon-sm"
    expect(html).toContain("hover:bg-muted"); // ghost
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });
});

describe("SkipLink", () => {
  it("targets #main by default and is hidden until focus", () => {
    const html = renderToStaticMarkup(<SkipLink />);
    expect(html).toContain('href="#main"');
    expect(html).toContain("Skip to content");
    // parked off-screen by default, restored on keyboard focus
    expect(html).toContain("-translate-y-[200%]");
    expect(html).toContain("focus-visible:translate-y-0");
  });

  it("accepts a custom target and label", () => {
    const html = renderToStaticMarkup(<SkipLink href="#content">Jump in</SkipLink>);
    expect(html).toContain('href="#content"');
    expect(html).toContain("Jump in");
  });
});
