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
// code is MIT and free to self-host, and what is sold is the integration work.

const WORK: { label: string; body: string }[] = [
  {
    label: "Deploy the stack",
    body:
      "Set up the modules you need in your environment and document how they run, connect and " +
      "recover",
  },
  {
    label: "Connect your systems",
    body:
      "Integrate your model providers, identity layer, data sources, retrieval backends and " +
      "existing services",
  },
  {
    label: "Build on digithings",
    body:
      "Develop agent workflows, MCP tools, retrieval pipelines or a customer-facing application " +
      "on the same modules and engineering standards as the core stack",
  },
  {
    label: "Hand over the work",
    body:
      "Deliver source code, tests, operating documentation and CI checks in infrastructure your " +
      "team controls",
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
            <PageTitle title="Build on digithings, in your environment.">
              The software is MIT-licensed and free to self-host. What we sell is the integration
              work — fitting these modules to the systems you already run.
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
            lede="Tell us what you run today, what you want to build and which constraints matter. We will determine whether digithings fits and define the deliverables, dependencies, responsibilities, timing and price in writing before work begins."
          >
            <Prose>
              <p>
                There are no public package prices or service-level commitments because the work is
                scoped for each environment. The repository remains available whether or not you
                engage us.
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
