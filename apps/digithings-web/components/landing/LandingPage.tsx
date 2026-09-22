"use client";

import { ContactMailto, CopyCommand, CtaLink, SocialRow } from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { ArgumentClaims, ArgumentCta, ArgumentSeams } from "@/components/landing/Argument";
import { BootTerminal } from "@/components/landing/BootTerminal";
import { ContactForm } from "@/components/landing/ContactForm";
import { ModuleGrid } from "@/components/landing/ModuleGrid";
import { Pricing } from "@/components/landing/Pricing";
import { QuantSection } from "@/components/landing/QuantSection";
import { QuickAsk } from "@/components/landing/QuickAsk";
import { FaqList, OpenSource, Testimonials } from "@/components/landing/Sections";
import { REPO_CLONE } from "@/lib/repoActivity";

/**
 * The landing page body (v15, #4429).
 *
 * The `lean` profile from v14, which the owner picked and which the v15 pass
 * refines; the other two profiles and the review switcher are gone.
 *
 * The honesty rules are unchanged: no performance figures, open weights "at par
 * or close", no live-trading promise, hosted MCP spelled as roadmap. Cutting
 * sections only ever *removes* assertions, never rewords one.
 */

/** The hero: the statement piece, and nothing else. */
function Hero() {
  return (
    <section className="px-[var(--page-pad)] pb-0 pt-[clamp(3rem,6vw,5rem)]">
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col">
        <span className="animate-appear inline-flex w-fit items-center gap-[0.5rem] border border-hair px-[0.7rem] py-[0.25rem] font-mono text-[0.68rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute opacity-0">
          open core · MIT · self-hosted
        </span>

        <h1 className="animate-appear relative z-10 mt-[1.4rem] mb-0 font-mono text-[clamp(1.45rem,3.1vw,2.6rem)] font-medium leading-[1.15] tracking-[-0.03em] text-ink opacity-0 delay-100">
          AI infrastructure,{" "}
          <span className="text-accent">in a glass box you own.</span>
        </h1>
      </div>
    </section>
  );
}

/**
 * The boot terminal, beside the clone command (v15 point 7).
 *
 * The terminal is a fixed-height box on the right and never grows as it types
 * (`size="compact"` + `fill`); the clone command and the two CTAs sit on the
 * left. The clone is shown on its own line — the `make up` that follows it is
 * the terminal's first line, right beside it. On narrow viewports the two stack
 * and the terminal keeps a fixed height so the section does not jump.
 */
function Boot() {
  return (
    <section className="line-b px-[var(--page-pad)] py-[var(--section-y-tight)]">
      <div className="mx-auto grid max-w-[var(--frame-w)] grid-cols-[minmax(0,1fr)] gap-[1.6rem] min-[900px]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] min-[900px]:items-stretch">
        {/* `justify-between` over two clusters, not `justify-center` over three
            children: the terminal beside this is ~465px tall, so centring
            ~135px of copy left ~165px of dead space directly under the hero and
            the page's first screen read as two unrelated halves. Grouping the
            label with the command and pinning the CTAs to the bottom instead
            puts the clone instruction at the terminal's title bar and the two
            actions on its last line, so the cells read as one object. Below
            900px the grid is single-column and the cell is auto-height, so this
            has no effect there. */}
        <div className="flex min-w-0 flex-col justify-between gap-[1.2rem]">
          <div className="flex flex-col gap-[1.2rem]">
            <p className="animate-appear m-0 font-mono text-[0.7rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute opacity-0">
              clone it · one make up brings the stack up
            </p>
            <CopyCommand
              samples={[{ label: "clone", protocol: "git clone", code: REPO_CLONE }]}
              ariaLabel="Clone command"
              inline
            />
          </div>
          <div className="flex flex-wrap items-center gap-[0.8rem]">
            <CtaLink href="/docs">Read the docs</CtaLink>
            <CtaLink href="/chat" variant="ghost">
              Ask digichat
            </CtaLink>
          </div>
        </div>
        <BootTerminal className="animate-appear min-h-[420px] min-w-0 opacity-0 delay-100 min-[900px]:min-h-0" />
      </div>
    </section>
  );
}

/**
 * The module-grid header, and the page's `#architecture` anchor.
 *
 * The nav and the footer both link `/#architecture`, which was a real section on
 * the pre-rebuild page ("Nine modules. One toolkit." over the module manifest).
 * The redesign replaced that section with this header plus the mosaic but left
 * the nav pointing at it, so the anchor had no target and the link scrolled
 * nowhere. The id lives here rather than on the mosaic itself because this is
 * where a reader arriving from the nav should land: the heading, with the
 * modules pinned directly below it.
 */
function StackHeader() {
  return (
    <section id="architecture" className="line-t px-[var(--page-pad)] pt-[var(--section-y-tight)]">
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[1.2rem]">
        <h2 className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
          Every module, one at a time
        </h2>
      </div>
    </section>
  );
}

/**
 * The contact section, shared verbatim with the full profile's two-column shape.
 *
 * Point 14 ("swap form and contact info") is already the arrangement here: the
 * email form is the left column and the copy plus CTAs are the right, so the
 * band alternates against the FAQ band above it (FAQ left / chat right). The
 * verification pass measured the two columns at x=130 (form) and x=753 (info)
 * and changed nothing — moving the form would have broken the requested order.
 */
function Contact() {
  return (
    <section id="contact" className="px-[var(--page-pad)] py-[var(--page-step)]">
      <div className="mx-auto grid max-w-[var(--frame-w)] gap-[2.4rem] min-[960px]:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <div className="border border-hair bg-surface p-[1.6rem]">
          <ContactForm />
        </div>
        <div className="flex flex-col gap-[1.4rem]">
          <h2 className="m-0 max-w-[24ch] font-mono text-[length:var(--type-page-title)] font-medium leading-[1.2] tracking-[-0.02em] text-balance text-ink">
            You own the stack, the keys, and the infrastructure.
          </h2>
          <p className="m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            The whole monorepo is MIT-licensed and public — take it and run it yourself. What we sell
            is the integration work: fitting these modules to the stack you already have.
          </p>
          <div className="flex flex-wrap items-center gap-[0.8rem]">
            <ContactMailto
              email={DT_CONTACT_EMAIL}
              className={buttonVariants({ variant: "ghost" })}
              subject="digithings%20inquiry"
            >
              Email us instead
            </ContactMailto>
            <CtaLink href="/docs" variant="ghost">
              Read the docs
            </CtaLink>
            <span className="font-mono text-[0.8rem] text-ink-mute">
              <ContactMailto email={DT_CONTACT_EMAIL} showAddress>
                {DT_CONTACT_EMAIL}
              </ContactMailto>
            </span>
          </div>
          <div>
            <SocialRow />
          </div>
        </div>
      </div>
    </section>
  );
}

export function LandingPage() {
  return (
    <>
      <Hero />
      <Boot />
      <StackHeader />
      <ModuleGrid />

      <section id="why" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          <h2 className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
            Why digithings, not the ready-made platform
          </h2>
          {/* Point 10: the argument is the picture, not a column of prose. */}
          <ArgumentSeams />
          <ArgumentClaims />
          <ArgumentCta />
        </div>
      </section>

      <section id="open-source" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          <h2 className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
            Open source, and still moving
          </h2>
          <OpenSource />
        </div>
      </section>

      <section id="digiquant" className="relative px-[var(--page-pad)] py-[var(--page-step)]">
        <QuantSection />
      </section>

      <section id="pricing" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          <h2 className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
            The software is free. The integration is the work.
          </h2>
          <Pricing />
        </div>
      </section>

      <section id="voices" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          <h2 className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
            Two voices, both real
          </h2>
          {/* Point 5: the quotes are one section now, not a band and a hero line. */}
          <Testimonials />
        </div>
      </section>

      <section id="faq" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto grid max-w-[var(--frame-w)] gap-[2.4rem] min-[960px]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-[1.6rem]">
            <h2 className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
              Questions, answered
            </h2>
            <FaqList />
          </div>
          <QuickAsk className="min-w-0" />
        </div>
      </section>

      <Contact />
    </>
  );
}
