import type { Metadata } from "next";
import {
  ContactMailto,
  CtaLink,
  DocumentFrame,
  GlyphList,
  GlyphRow,
  PageTitle,
  Prose,
  Section,
} from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "services — integrate digithings into your environment",
  description:
    "Get help deploying digithings, connecting it to your systems, and building applications on " +
    "top of the open-source stack.",
};

// /services — rebuilt on the document grammar (D1, #4429): one framed column,
// hairline-separated sections, the `[*]` row grammar. Three sections — what we
// do, how an engagement starts, and the contact. The honesty framing leads: the
// code is MIT with no license fee, and what is sold is the integration work.

const WORK: { label: string; body: string }[] = [
  {
    label: "Deploy the stack",
    body:
      "We set up the modules you need in your environment and document how they run, connect " +
      "and recover",
  },
  {
    label: "Connect your systems",
    body:
      "We integrate your model providers, identity layer, data sources, retrieval backends and " +
      "existing services",
  },
  {
    label: "Build on digithings",
    body:
      "We develop agent workflows, MCP tools, retrieval pipelines or a customer-facing application " +
      "on the same modules and engineering standards as the core stack",
  },
  {
    label: "Hand over the work",
    body:
      "You get the source code, tests, operating documentation and CI checks, in infrastructure " +
      "your team controls",
  },
];

const CONTEXT: { label: string; body: string }[] = [
  {
    label: "Useful context",
    body:
      "Your current infrastructure and deployment target, the data, providers and services that " +
      "must connect, the workflow or application your users need, and your security, compliance " +
      "and operating constraints",
  },
];

export default function ServicesPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle path="services" title="Build on digithings, in your environment.">
              The software is MIT-licensed and runs on your own hardware with no license fee. What
              we offer is the integration work: fitting these modules to the systems you already
              run.
            </PageTitle>
          </div>

          <Section
            id="what-we-do"
            title="What we do"
            lede="Start with the modules you need, connect them to the systems you already run, and leave with code and documentation your team owns."
          >
            <GlyphList>
              {WORK.map((r) => (
                <GlyphRow key={r.label} label={r.label}>
                  {r.body}
                </GlyphRow>
              ))}
            </GlyphList>
          </Section>

          <Section
            id="engagement"
            title="How an engagement starts"
            lede="Tell us what you run today, what you want to build and which constraints matter. We will tell you plainly whether digithings fits, then put the deliverables, dependencies, responsibilities, timing and price in writing before work begins."
          >
            <Prose>
              <p>
                There are no fixed packages or published service levels, because every engagement is
                scoped to its environment. The repository stays open to you whether or not you
                work with us.
              </p>
            </Prose>
            <div className="mt-[1.6rem]">
              <GlyphList>
                {CONTEXT.map((r) => (
                  <GlyphRow key={r.label} label={r.label}>
                    {r.body}
                  </GlyphRow>
                ))}
              </GlyphList>
            </div>
          </Section>

          <Section
            id="contact"
            title="Contact"
            lede="A short note about your environment and intended outcome is enough to start the conversation."
          >
            <div className="flex flex-wrap items-center gap-[0.8rem]">
              <ContactMailto
                email={DT_CONTACT_EMAIL}
                className={buttonVariants({ variant: "default" })}
                subject="digithings%20services%20inquiry"
              >
                Email about a project
              </ContactMailto>
              <CtaLink href="/docs" variant="ghost">
                Read the docs
              </CtaLink>
              <CtaLink href="/security" variant="ghost">
                Review security
              </CtaLink>
              <span className="font-mono text-[length:var(--type-body)] text-ink-mute">
                <ContactMailto email={DT_CONTACT_EMAIL} showAddress>
                  {DT_CONTACT_EMAIL}
                </ContactMailto>
              </span>
            </div>
          </Section>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
