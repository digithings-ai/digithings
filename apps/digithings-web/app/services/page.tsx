import type { Metadata } from "next";
import { ContactMailto, CtaLink, PageHead, RuledList, RuledRow } from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { DtFooter } from "@/components/DtFooter";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "services — integrate digithings into your environment",
  description:
    "Get help deploying digithings, connecting it to your systems, and building applications on " +
    "top of the open-source stack.",
};

const WORK = [
  {
    term: "Deploy the stack",
    body:
      "Set up the modules you need in your environment and document how they run, connect, and " +
      "recover.",
  },
  {
    term: "Connect your systems",
    body:
      "Integrate your model providers, identity layer, data sources, retrieval backends, and " +
      "existing services.",
  },
  {
    term: "Build on digithings",
    body:
      "Develop agent workflows, MCP tools, retrieval pipelines, or a customer-facing application " +
      "using the same modules and engineering standards as the core stack.",
  },
  {
    term: "Hand over the work",
    body:
      "Deliver source code, tests, operating documentation, and CI checks in infrastructure your " +
      "team controls.",
  },
];

export default function ServicesPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <PageHead
          kicker={"// services"}
          title={
            <>
              Build on digithings <em>in your environment.</em>
            </>
          }
        >
          The software is MIT-licensed and free to self-host. We provide implementation services
          for teams that want help integrating the stack or building an application on top of it.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// what we do"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              Start with the modules you need, connect them to the systems you already run, and
              leave with code and documentation your team owns.
            </p>
            <RuledList>
              {WORK.map((item) => (
                <RuledRow key={item.term} term={item.term}>
                  {item.body}
                </RuledRow>
              ))}
            </RuledList>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <span className="kicker">{"// how an engagement starts"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              Tell us what you run today, what you want to build, and which constraints matter. We
              will determine whether digithings fits and define the deliverables, dependencies,
              responsibilities, timing, and price in writing before work begins.
            </p>
            <p className="mt-[1rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
              There are no public package prices or service-level commitments because the work is
              scoped for each environment. The repository remains available whether or not you
              engage us.
            </p>
            <RuledList>
              <RuledRow term="Useful context">
                Your current infrastructure and deployment target; the data, providers, and services
                that must connect; the workflow or application your users need; and your security,
                compliance, and operating constraints.
              </RuledRow>
            </RuledList>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// contact"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              A short note about your environment and intended outcome is enough to start the
              conversation.
            </p>
            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
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
              <span className="font-mono text-[0.82rem] text-ink-mute">
                <ContactMailto email={DT_CONTACT_EMAIL} showAddress>
                  {DT_CONTACT_EMAIL}
                </ContactMailto>
              </span>
            </div>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
