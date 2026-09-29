"use client";

import { ContactMailto, CopyCommand, CtaLink, Reveal, SocialRow } from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { ContactForm } from "@/components/landing/ContactForm";
import { FaqMorph } from "@/components/landing/FaqMorph";
import { ModuleGrid } from "@/components/landing/ModuleGrid";
import { Pricing } from "@/components/landing/Pricing";
import { QuantSection } from "@/components/landing/QuantSection";
import { SectionRail } from "@/components/landing/SectionRail";
import { OpenSource } from "@/components/landing/Sections";
import { WhyStack } from "@/components/landing/WhyStack";
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
 * The hero: the statement piece, the mission, and the clone command.
 *
 * The owner's direction for this round: split the title over two lines, add a
 * one-to-two-sentence mission statement beneath it, then the clone command —
 * and remove the deployment terminal, with the module grid moving up to sit
 * directly under the hero. So this section is a single left-aligned column:
 * the two-line h1, the mission paragraph, and the clone command (which moves
 * up from the old `Boot` band. The clone box is natural width — just the
 * size of the text inside it (owner direction); no full-frame override.
 * The terminal, its glow and its frame are gone.
 */
function Hero() {
  return (
    <section className="px-[var(--page-pad)] pb-[clamp(0.75rem,2vw,1.5rem)] pt-[clamp(3rem,6vw,5rem)]">
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[1.4rem]">
        <p className="animate-appear m-0 font-mono text-[0.75rem] tracking-[0.04em] text-ink-mute opacity-0">
          ~/digithings · open core · MIT
        </p>
        <h1 className="animate-appear relative z-10 m-0 font-mono text-[clamp(1.45rem,3.1vw,2.6rem)] font-medium leading-[1.15] tracking-[-0.03em] text-ink opacity-0 [animation-delay:90ms]">
          <span className="block">AI infrastructure,</span>
          <span className="block text-accent">
            in a glass box you own.
            <span
              className="ms-[0.25em] inline-block h-[0.82em] w-[0.5em] bg-accent align-[-0.08em] [animation:chat-cursor-blink_1.1s_steps(1)_infinite] motion-reduce:[animation:none]"
              aria-hidden="true"
            />
          </span>
        </h1>
        <p className="animate-appear m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft opacity-0 [animation-delay:200ms]">
          digithings is open-core AI infrastructure you run yourself: chat,
          research and quant modules on your own keys and hardware. The code
          is MIT-licensed. What we sell is the work of fitting it to your stack.
        </p>
        {/* Natural width (owner direction): the box is only as wide as the
            command text inside it. `CopyCommand` caps itself at the prose
            measure on its own — no width override. */}
        <div className="animate-appear opacity-0 [animation-delay:320ms]">
          <CopyCommand
            samples={[{ label: "clone", protocol: "git clone", code: REPO_CLONE }]}
            ariaLabel="Clone command"
            inline
          />
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
        <Reveal className="border border-hair bg-surface p-[1.6rem]">
          <ContactForm />
        </Reveal>
        <Reveal delay={0.08} className="flex flex-col gap-[1.4rem]">
          <h2 className="m-0 max-w-[24ch] font-mono text-[length:var(--type-page-title)] font-medium leading-[1.2] tracking-[-0.02em] text-balance text-ink">
            You own the stack and the keys.
          </h2>
          <p className="m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            The monorepo is MIT-licensed and public. What we sell is the
            integration work: fitting these modules to the systems you already run.
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
          <Reveal as="h2" className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
            Open source, and still shipping
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
        <Reveal className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
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
