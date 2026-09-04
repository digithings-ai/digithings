import type { Metadata } from "next";
import Link from "next/link";
import { Reveal } from "@digithings/web";
import { DtFooter } from "@/components/DtFooter";
import { PageHead, RuledList, RuledRow } from "../_company/prose";
import { ContactMailto } from "@digithings/web";
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
            <Reveal className="section-head">
              <span className="kicker">{"// what we do"}</span>
              <h2>From repository to working system.</h2>
              <p>
                Start with the modules you need, connect them to the systems you already run, and
                leave with code and documentation your team owns.
              </p>
            </Reveal>
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
          <div className="wrap grid gap-[3rem] lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.5fr)]">
            <div>
              <span className="kicker">{"// how an engagement starts"}</span>
              <h2 className="mt-[0.8rem] max-w-[18ch] text-[clamp(1.8rem,4vw,3rem)] leading-[1.08] text-ink">
                Scope the outcome before the work.
              </h2>
              <p className="mt-[1.1rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
                Tell us what you run today, what you want to build, and which constraints matter.
                We will determine whether digithings fits and define the deliverables, dependencies,
                responsibilities, timing, and price in writing before work begins.
              </p>
              <p className="mt-[1rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
                There are no public package prices or service-level commitments because the work is
                scoped for each environment. The repository remains available whether or not you
                engage us.
              </p>
            </div>

            <div className="border-t border-hair pt-[1.4rem] lg:border-l lg:border-t-0 lg:pl-[1.8rem] lg:pt-0">
              <span className="block font-mono text-[0.7rem] uppercase tracking-[0.14em] text-ink-mute">
                Useful context to include
              </span>
              <ul className="mt-[1rem] grid list-none gap-[0.75rem] p-0 text-[0.9rem] leading-[1.65] text-ink-soft">
                <li>Your current infrastructure and deployment target</li>
                <li>The data, providers, and services that must connect</li>
                <li>The workflow or application your users need</li>
                <li>Your security, compliance, and operating constraints</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// contact"}</span>
              <h2>Describe the system you want to build.</h2>
              <p>
                A short note about your environment and intended outcome is enough to start the
                conversation.
              </p>
            </Reveal>
            <div className="flex flex-wrap gap-[0.8rem]">
              <ContactMailto email={DT_CONTACT_EMAIL} className="btn btn-primary" subject="digithings%20services%20inquiry">
                Email about a project <span aria-hidden="true">→</span>
              </ContactMailto>
              <Link className="btn btn-ghost" href="/docs">
                Read the docs
              </Link>
              <Link className="btn btn-ghost" href="/security">
                Review security
              </Link>
            </div>
            <p className="mt-[1.4rem] font-mono text-[0.88rem] text-ink-mute">
              <ContactMailto email={DT_CONTACT_EMAIL}
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                showAddress
              >
                Or email us directly
              </ContactMailto>
            </p>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
