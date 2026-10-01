"use client";

import type { CSSProperties } from "react";
import { ContactMailto, CopyCommand, CtaLink, Reveal, SocialRow } from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { ContactForm } from "@/components/landing/ContactForm";
import { PixelField } from "@/components/landing/PixelField";
import { PixelWordmark } from "@/components/landing/PixelWordmark";
import { FaqMorph } from "@/components/landing/FaqMorph";
import { ModuleGrid } from "@/components/landing/ModuleGrid";
import { Pricing } from "@/components/landing/Pricing";
import { QuantSection } from "@/components/landing/QuantSection";
import { SectionRail } from "@/components/landing/SectionRail";
import { SectionHead } from "@/components/landing/SectionHead";
import { OpenSource } from "@/components/landing/Sections";
import { WhyStack } from "@/components/landing/WhyStack";
import { REPO_CLONE, REPO_URL } from "@/lib/repoActivity";

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
 * The hero: the pixel welcome, then the clone command.
 *
 * The field and the pixel wordmark are the gloom lockup the owner picked.
 * The clone box is only as wide as the command. GitHub and the module jump
 * sit on the same row, to its right.
 */
const HERO_ACTION =
  "hero-action inline-flex h-auto items-center border border-hair bg-transparent px-[1rem] py-[0.85rem] font-mono text-[0.85rem] leading-[1.5] text-ink no-underline hover:bg-surface-2";

/** What the hero promises, each line already stated in the FAQ below it. */
const HERO_FACTS = ["self-hosted", "your own keys", "no hosted tier"] as const;

function rise(step: number): CSSProperties {
  return { "--rise": step } as CSSProperties;
}

function Hero() {
  return (
    <section className="pixel-hero border-b border-hair">
      <PixelField />
      <div className="relative z-10 mx-auto flex max-w-[64rem] flex-col items-center px-[var(--page-pad)] pb-[6rem] pt-[2.5rem] text-center sm:px-[2.5rem] sm:pb-[7rem]">
        <PixelWordmark />
        <h1
          className="hero-rise m-0 mt-[2rem] font-display text-[1.5rem] font-semibold leading-[1.25] tracking-[-0.02em] text-balance text-ink sm:text-[1.7rem]"
          style={rise(0)}
        >
          AI infrastructure, in a glass box you own.
        </h1>
        <p
          className="hero-rise m-0 mt-[0.75rem] max-w-[42rem] text-[0.9375rem] leading-[1.6] text-pretty text-ink-soft"
          style={rise(1)}
        >
          Chat, research and quant modules on your own keys and hardware.
        </p>
        <div
          className="hero-rise mt-[1.75rem] flex max-w-full flex-wrap items-center justify-center gap-[0.65rem]"
          style={rise(2)}
        >
          <CopyCommand
            className="w-fit max-w-full"
            samples={[{ label: "clone", protocol: "git clone", code: REPO_CLONE }]}
            ariaLabel="Clone command"
            inline
          />
          <CtaLink href={REPO_URL} external variant="ghost" className={HERO_ACTION}>
            GitHub
          </CtaLink>
          <CtaLink href="#architecture" variant="ghost" className={HERO_ACTION}>
            Modules
            <span aria-hidden="true" className="hero-action__arrow">
              ↓
            </span>
          </CtaLink>
        </div>
        <ul
          className="hero-rise m-0 mt-[1.4rem] flex list-none flex-wrap items-center justify-center gap-x-[0.6rem] gap-y-[0.3rem] p-0 font-mono text-[0.72rem] leading-[1.5] tracking-[0.02em] text-ink-mute"
          style={rise(3)}
          aria-label="What you get"
        >
          {HERO_FACTS.map((fact, index) => (
            <li key={fact} className="flex items-center gap-[0.6rem]">
              {index > 0 ? <span aria-hidden="true" className="text-hair">/</span> : null}
              {fact}
            </li>
          ))}
        </ul>
      </div>
      <a href="#architecture" className="hero-cue" aria-label="Scroll to the modules">
        <span aria-hidden="true" className="hero-cue__line" />
      </a>
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
        <Reveal className="border border-hair bg-surface p-[1.6rem]">
          <ContactForm />
        </Reveal>
        <Reveal delay={0.08} className="flex flex-col gap-[1.4rem]">
          <SectionHead
            id="contact"
            title="You own the stack and the keys."
            titleClassName="max-w-[24ch]"
          />
          <p className="m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            What we sell is the integration work: fitting these modules to the
            systems you already run.
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
        </Reveal>
      </div>
    </section>
  );
}

export function LandingPage({ embedOrigin }: { embedOrigin: string }) {
  return (
    <>
      <SectionRail />
      <Hero />
      <ModuleGrid />

      {/* The app-first band: three apps with their own provider architectures, a
          guided walk, a box-by-box morph to the digithings stack, and a
          sticky live invoice. `WhyStack` is a thin alias for it; the section
          keeps only the anchor and the band rules. */}
      <section id="why" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <WhyStack />
      </section>

      <section id="open-source" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          <Reveal>
            <SectionHead
              id="open-source"
              title="Open source, and still shipping"
              lede="Clone it, read it, run it. The activity below is the repo's own."
            />
          </Reveal>
          <Reveal delay={0.08}>
            <OpenSource />
          </Reveal>
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

      {/* No section title here by owner direction (#4429 ship list): the
          comparison table suffices on its own. */}
      <section id="pricing" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        <Reveal className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[1.25rem]">
          <SectionHead id="pricing" />
          <Pricing />
        </Reveal>
      </section>

      <section id="faq" className="line-b px-[var(--page-pad)] py-[var(--page-step)]">
        {/* The band's inner grid now rides the scroll-driven zoom-morph: the
            chat starts large over the frame and retracts into the right column
            as the FAQ list rises in on the left. The two-column grid, the h2,
            the `details` list and the `full screen chat` control are all owned
            by `<FaqMorph/>`; see its docblock for the mechanics and the
            reduced-motion / no-JS fallback. */}
        <FaqMorph embedOrigin={embedOrigin} />
      </section>

      <Contact />
    </>
  );
}
