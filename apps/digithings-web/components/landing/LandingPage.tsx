"use client";

import { ContactMailto, CopyCommand, CtaLink, Glow, MockupFrame, SocialRow } from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { ArgumentSeams } from "@/components/landing/Argument";
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

/**
 * The hero: the statement piece, and nothing else.
 *
 * The owner's direction for this round: "open core mit self-hosted remove that
 * just keep the title then i would place everything left aligned". The eyebrow
 * badge is gone, so the h1 is the whole hero and the section is a single
 * left-aligned column — which is what the frame already was; the badge was the
 * only thing that made it read as a two-item stack.
 */
function Hero() {
  return (
    <section className="px-[var(--page-pad)] pb-0 pt-[clamp(3rem,6vw,5rem)]">
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col">
        <h1 className="animate-appear relative z-10 m-0 font-mono text-[clamp(1.45rem,3.1vw,2.6rem)] font-medium leading-[1.15] tracking-[-0.03em] text-ink opacity-0">
          AI infrastructure,{" "}
          <span className="text-accent">in a glass box you own.</span>
        </h1>
      </div>
    </section>
  );
}

/**
 * The clone command, with the deployment terminal beneath it (round 2).
 *
 * The owner's direction: "just have the git clone button and the terminal
 * should be below it" — so the eyebrow label is gone, the two CTAs are gone
 * (they were the first of the "read the docs buttons all over the place" this
 * round removes), and the band is a single left-aligned column. The clone
 * command is the call to action here; it is the one thing a reader can act on.
 *
 * The terminal's height is now fixed, and that is a bug fix rather than a
 * tidy-up. It used to be content-sized, so every line the script typed grew the
 * box and pushed the rest of the page down as you watched it — the owner's "it
 * shifts the website down". A definite height plus the primitive's `fill` (which
 * sets `min-height: 0` and `overflow: hidden` on the body) means the box is the
 * same size from the first frame to the last and the typed lines simply fill it.
 *
 * `Glow` + `MockupFrame` give it the kit's depth treatment — both were built for
 * exactly this in D1 and went unused until this branch. The frame is a
 * translucent bezel around the terminal's own surface and shadow; `Glow` lays a
 * soft radial light behind it, reading `--accent`, which this app collapses to
 * neutral ink, so the wash is white and the monochrome canon holds.
 *
 * `overflow-x-clip` on the section is load-bearing, not tidying: the glow's
 * ellipses are `w-[60%]` at `scale-[2.5]`, so they render ~2.5x wider than the
 * band and would otherwise push the document 67px past the viewport at 390px
 * (measured 457 vs 390). `clip` rather than `hidden` so the band is not turned
 * into a scroll container, and only on the x axis so the light still bleeds
 * vertically.
 */
function Boot() {
  return (
    <section className="line-b overflow-x-clip px-[var(--page-pad)] py-[var(--section-y-tight)]">
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[1.6rem]">
        {/* `*:max-w-none` because `CopyCommand` caps itself at the prose
            measure (691px). Alone that reads fine, but the terminal directly
            beneath it spans the whole frame (1164px), so the band's two
            elements disagreed about the column. The command is chrome, not
            prose — it should share the terminal's width. */}
        <div className="[&>*]:max-w-none">
          <CopyCommand
            samples={[{ label: "clone", protocol: "git clone", code: REPO_CLONE }]}
            ariaLabel="Clone command"
            inline
          />
        </div>
        <div className="relative min-w-0">
          <Glow variant="top" />
          <MockupFrame size="small" className="animate-appear opacity-0 delay-100">
            <BootTerminal className="h-[clamp(18.5rem,30vh,20.5rem)] min-w-0" />
          </MockupFrame>
        </div>
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
      <ModuleGrid />

      <section id="why" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          <h2 className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
            Why digithings, not the ready-made platform
          </h2>
          {/* Point 10: the argument is the picture, not a column of prose.
              Round 3: the comparison is the whole section — the three claims
              that used to sit below the diagram are retired. */}
          <ArgumentSeams />
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

      {/* No horizontal padding here: the digiquant band paints its own tinted
          background and the owner asked for it full width ("make the background
          of the digiquant section expand the full width… its own background").
          QuantSection owns both the padding and the frame, so the background
          reaches the viewport edges while the content stays on the page grid. */}
      <section id="digiquant" className="relative">
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
